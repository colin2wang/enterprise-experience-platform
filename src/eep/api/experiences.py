"""Experience library + action follow-up + evolution chain routes.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eep.db import get_session
from eep.db.models import Experience, Meeting, Relation, User
from eep.api.params import parse_uuid
from eep.memory.service import MemoryService
from eep.schemas import (
    ChainCard,
    ChainOut,
    ExperienceOut,
    ExperiencePatch,
    ExperienceStatus,
    ExperienceType,
    Swimlane,
)

router = APIRouter()

TYPE_PLACEHOLDER = {
    "question": "No questions identified yet",
    "hypothesis": "No hypotheses identified yet",
    "experiment": "No experiments identified yet",
    "decision": "No decisions identified yet",
    "action": "No actions identified yet",
}


def _to_out(e: Experience, owner_name: str | None = None) -> ExperienceOut:
    return ExperienceOut(
        id=str(e.id),
        code=e.code,
        type=e.type,  # type: ignore[arg-type]
        title=e.title,
        description=e.description,
        status=e.status,
        owner_id=str(e.owner_id) if e.owner_id else None,
        owner_name=owner_name,
        due_date=e.due_date,
        acceptance_criteria=e.acceptance_criteria,
        source_meeting_id=str(e.source_meeting_id) if e.source_meeting_id else None,
        source_span=e.source_span or {},
        updated_at=e.updated_at,
    )


async def _owner_names(session: AsyncSession, exps: list[Experience]) -> dict[str, str]:
    """Batch-resolve owner display names."""
    ids = {e.owner_id for e in exps if e.owner_id}
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {str(u.id): u.name for u in rows}


# --------------------------------------------------------------------- #
# Experience list / detail / patch / claim
# --------------------------------------------------------------------- #
@router.get("/projects/{pid}/experiences", response_model=list[ExperienceOut])
async def list_experiences(
    pid: str,
    type: ExperienceType | None = Query(default=None),
    status: ExperienceStatus | None = Query(default=None),
    owner: str | None = Query(default=None),
    q: str | None = Query(default=None),
    sort: str = Query(default="-updated"),
    session: AsyncSession = Depends(get_session),
) -> list[ExperienceOut]:
    """Experience library / action follow-up list (shared shape, M1)."""
    pid = parse_uuid(pid, "project id")
    stmt = select(Experience).where(Experience.project_id == pid)
    if type:
        stmt = stmt.where(Experience.type == type)
    if status:
        stmt = stmt.where(Experience.status == status)
    if owner == "unclaimed":
        stmt = stmt.where(Experience.owner_id.is_(None))
    elif owner:
        stmt = stmt.where(Experience.owner_id == owner)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(Experience.title.ilike(like) | Experience.description.ilike(like))
    if sort.startswith("-"):
        stmt = stmt.order_by(Experience.updated_at.desc())
    else:
        stmt = stmt.order_by(Experience.updated_at)
    rows = (await session.execute(stmt)).scalars().all()
    names = await _owner_names(session, list(rows))
    return [_to_out(e, names.get(str(e.owner_id))) for e in rows]


@router.get("/experiences/{eid}", response_model=ExperienceOut)
async def experience_detail(
    eid: str, session: AsyncSession = Depends(get_session)
) -> ExperienceOut:
    """Slide-over detail: fields + evidence + chain entry point."""
    e = await session.get(Experience, parse_uuid(eid, "experience id"))
    if e is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    owner_name = None
    if e.owner_id:
        owner = await session.get(User, e.owner_id)
        owner_name = owner.name if owner else None
    return _to_out(e, owner_name)


@router.patch("/experiences/{eid}", response_model=ExperienceOut)
async def patch_experience(
    eid: str,
    payload: ExperiencePatch,
    session: AsyncSession = Depends(get_session),
) -> ExperienceOut:
    """Edit fields; every change is written to change_log (audit)."""
    changes = payload.model_dump(exclude_none=True)
    memory = MemoryService(session)
    exp = await memory.patch_experience(eid, changes)
    if exp is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    await session.commit()
    await session.refresh(exp)  # onupdate server default expires updated_at after flush
    return _to_out(exp)


@router.post("/experiences/{eid}/claim", response_model=ExperienceOut)
async def claim_experience(
    eid: str,
    owner_id: str,
    session: AsyncSession = Depends(get_session),
) -> ExperienceOut:
    """Claim (or reassign) an action; change_log records the ownership change."""
    memory = MemoryService(session)
    exp = await memory.patch_experience(eid, {"owner_id": owner_id})
    if exp is None:
        raise HTTPException(status_code=404, detail="Experience not found")
    await session.commit()
    await session.refresh(exp)  # onupdate server default expires updated_at after flush
    owner = await session.get(User, exp.owner_id)
    return _to_out(exp, owner.name if owner else None)


# --------------------------------------------------------------------- #
# Evolution chain (swimlane view)
# --------------------------------------------------------------------- #
@router.get("/experiences/{eid}/chain", response_model=ChainOut)
async def experience_chain(
    eid: str, session: AsyncSession = Depends(get_session)
) -> ChainOut:
    """Five-lane swimlane: experiences connected to this one, by meeting date."""
    seed = await session.get(Experience, parse_uuid(eid, "experience id"))
    if seed is None:
        raise HTTPException(status_code=404, detail="Experience not found")

    edges = (
        await session.execute(
            select(Relation).where((Relation.from_exp == eid) | (Relation.to_exp == eid))
        )
    ).scalars().all()

    member_ids = {seed.id}
    for edge in edges:
        member_ids.update((edge.from_exp, edge.to_exp))
    rows = (
        await session.execute(select(Experience).where(Experience.id.in_(member_ids)))
    ).scalars().all()
    rows = sorted(rows, key=lambda e: e.t_event or date.min)

    lanes: list[Swimlane] = []
    for t in ("question", "hypothesis", "experiment", "decision", "action"):
        cards = [
            ChainCard(
                experience=_to_out(e),
                meeting_date=e.t_event,
                evidence_span=e.source_span or {},
            )
            for e in rows
            if e.type == t
        ]
        lanes.append(
            Swimlane(type=t, cards=cards, placeholder=TYPE_PLACEHOLDER[t] if not cards else "")
        )

    dates = [e.t_event for e in rows if e.t_event]
    return ChainOut(
        topic=seed.title,
        time_span=[min(dates) if dates else None, max(dates) if dates else None],
        relation_count=len(edges),
        lanes=lanes,
    )


@router.get("/projects/{pid}/chain/topics")
async def chain_topics(
    pid: str, q: str | None = Query(default=None), session: AsyncSession = Depends(get_session)
) -> list[dict[str, object]]:
    """Topic search for the chain landing page (N meetings, M relations)."""
    pid = parse_uuid(pid, "project id")
    stmt = select(Experience).where(Experience.project_id == pid)
    if q:
        stmt = stmt.where(Experience.title.ilike(f"%{q}%"))
    rows = (await session.execute(stmt.limit(20))).scalars().all()
    topics: list[dict[str, object]] = []
    for e in rows:
        rel_count = await session.scalar(
            select(func.count())
            .select_from(Relation)
            .where((Relation.from_exp == e.id) | (Relation.to_exp == e.id))
        )
        meet_count = await session.scalar(
            select(func.count(func.distinct(Meeting.id)))
            .select_from(Meeting)
            .join(Experience, Experience.source_meeting_id == Meeting.id)
            .where(Experience.id == e.id)
        )
        topics.append(
            {
                "id": str(e.id),
                "title": e.title,
                "type": e.type,
                "meeting_count": meet_count or 0,
                "relation_count": rel_count or 0,
            }
        )
    return topics
