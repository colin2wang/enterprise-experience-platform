"""Meetings + review + overview routes.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eep.api.params import parse_uuid as _parse_uuid
from eep.ai_providers import ModelFactory, ProviderSemaphores
from eep.checkpoints import get_checkpointer
from eep.codes import next_experience_code
from eep.config import load_ai_config
from eep.db import get_session
from eep.db.models import ExpMeeting, Experience, Extraction, Meeting, Project, User
from eep.graphs.ingestion import build_ingestion_graph
from eep.graphs.review import build_review_graph
from eep.memory.service import MemoryService
from eep.schemas import (
    ExperienceOutLite,
    MeetingCreate,
    MeetingDetailOut,
    MeetingOut,
    OverviewOut,
    ReviewSubmit,
)
from langgraph.types import Command

router = APIRouter()

logger = logging.getLogger("eep.api")

# Process-wide singletons (initialized in main.lifespan).
factory: ModelFactory | None = None
semaphores: ProviderSemaphores | None = None

# review_threads[thread_id] = suspended G2 state awaiting a verdict.
# Production: resolved from PostgresSaver checkpoints; this registry tracks
# locally created threads for the in-process dev flow.
review_threads: dict[str, dict[str, Any]] = {}


async def _ensure_project(session: AsyncSession, project_id: str) -> Project:
    proj = await session.get(Project, _parse_uuid(project_id, "project id"))
    if proj is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj


def _meeting_out(m: Meeting) -> MeetingOut:
    return MeetingOut(
        id=str(m.id),
        title=m.title,
        meet_date=m.meet_date,
        participants=m.participants or [],
        review_status=m.review_status,
        exp_stat_cache=m.exp_stat_cache or {},
    )


# --------------------------------------------------------------------- #
# Meetings
# --------------------------------------------------------------------- #
@router.get("/projects/{pid}/meetings", response_model=list[MeetingOut])
async def list_meetings(
    pid: str,
    q: str | None = Query(default=None),
    sort: str = Query(default="-date"),
    session: AsyncSession = Depends(get_session),
) -> list[MeetingOut]:
    """Meeting list with deposition statistics, newest first by default."""
    pid = _parse_uuid(pid, "project id")
    stmt = select(Meeting).where(Meeting.project_id == pid)
    if q:
        stmt = stmt.where(Meeting.title.ilike(f"%{q}%"))
    stmt = stmt.order_by(Meeting.meet_date.desc() if sort.startswith("-") else Meeting.meet_date)
    rows = (await session.execute(stmt)).scalars().all()
    return [_meeting_out(m) for m in rows]


@router.get("/meetings/{mid}", response_model=MeetingDetailOut)
async def meeting_detail(
    mid: str, session: AsyncSession = Depends(get_session)
) -> MeetingDetailOut:
    """Transcript viewer payload: summary + discussion + related experiences."""
    mid = _parse_uuid(mid, "meeting id")
    m = await session.get(Meeting, mid)
    if m is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    links = (
        await session.execute(
            select(ExpMeeting, Experience)
            .join(Experience, Experience.id == ExpMeeting.exp_id)
            .where(ExpMeeting.meeting_id == mid)
        )
    ).all()
    related = [
        ExperienceOutLite.model_validate(
            {
                "id": str(e.id),
                "code": e.code,
                "type": e.type,
                "title": e.title,
                "status": e.status,
            }
        )
        for _, e in links
    ]
    return MeetingDetailOut(
        **_meeting_out(m).model_dump(),
        summary=m.summary,
        discussion=m.discussion,
        related_experiences=related,  # type: ignore[arg-type]
    )


@router.post("/projects/{pid}/meetings", response_model=MeetingOut, status_code=201)
async def push_meeting(
    pid: str,
    payload: MeetingCreate,
    session: AsyncSession = Depends(get_session),
) -> MeetingOut:
    """Transcript push; triggers the G1 ingestion graph.

    Idempotency: (meeting, pipeline_version) unique index means a repeated
    push with the same pipeline version is rejected rather than re-run.
    """
    await _ensure_project(session, pid)
    m = Meeting(
        project_id=pid,
        title=payload.title,
        meet_date=payload.meet_date,
        participants=payload.participants,
        source_type=payload.source_type,
        review_status="pending",
        pipeline_version=payload.pipeline_version,
    )
    session.add(m)
    try:
        await session.flush()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=409, detail="Duplicate pipeline run") from exc

    # Run G1 in-process (AI writes only drafts; review still required).
    drafts: list[dict[str, Any]] = []
    g1 = build_ingestion_graph().compile()
    try:
        state = await g1.ainvoke(
            {
                "project_id": pid,
                "meeting_id": str(m.id),
                "transcript": payload.transcript_text,
                "drafts": [],
                "errors": [],
                "factory": factory,
                "semaphores": semaphores,
            }
        )
        drafts = state.get("drafts", [])
    except Exception:  # noqa: BLE001 - ingestion failure must not lose the meeting
        logger.exception("G1 ingestion failed for meeting %s", m.id)

    # Persist one extraction row per draft; each becomes a G2 review thread.
    for draft in drafts:
        session.add(
            Extraction(
                meeting_id=m.id,
                draft_json=draft,
                model_ver=factory.cfg.roles["extractor"].primary if factory else None,
                confidence=draft.get("confidence"),
                review_status="pending",
            )
        )
    if not drafts:
        session.add(
            Extraction(
                meeting_id=m.id,
                draft_json={"status": "queued"},
                model_ver=factory.cfg.roles["extractor"].primary if factory else None,
                review_status="pending",
            )
        )
    # Cache deposition stats for the meeting list (type distribution).
    type_counts: dict[str, int] = {}
    for d in drafts:
        type_counts[d.get("type", "unknown")] = type_counts.get(d.get("type", "unknown"), 0) + 1
    m.exp_stat_cache = {
        "total": len(drafts),
        "first_records": len(drafts),
        "type_distribution": type_counts,
    }
    await session.commit()
    return _meeting_out(m)


# --------------------------------------------------------------------- #
# Overview
# --------------------------------------------------------------------- #
@router.get("/projects/{pid}/overview", response_model=OverviewOut)
async def overview(pid: str, session: AsyncSession = Depends(get_session)) -> OverviewOut:
    """Aggregated decision-overview payload (metrics/attention/pilots/quotes)."""
    pid = _parse_uuid(pid, "project id")
    effective = await session.scalar(
        select(func.count())
        .select_from(Experience)
        .where(
            Experience.project_id == pid,
            Experience.type == "decision",
            Experience.status == "effective",
        )
    )
    open_actions = await session.scalar(
        select(func.count())
        .select_from(Experience)
        .where(Experience.project_id == pid, Experience.type == "action",
               Experience.status.in_(["pending", "in_progress"]))
    )
    total = await session.scalar(
        select(func.count()).select_from(Experience).where(Experience.project_id == pid)
    )
    meetings = await session.scalar(
        select(func.count()).select_from(Meeting).where(Meeting.project_id == pid)
    )
    attention = (
        await session.execute(
            select(Experience)
            .where(Experience.project_id == pid, Experience.status == "pending")
            .order_by(Experience.updated_at.desc())
            .limit(4)
        )
    ).scalars().all()
    pilots = (
        await session.execute(
            select(Experience).where(
                Experience.project_id == pid,
                Experience.type == "experiment",
                Experience.status == "planned",
            )
        )
    ).scalars().all()
    quotes = (
        await session.execute(
            select(Experience).where(
                Experience.project_id == pid,
                Experience.type == "decision",
                Experience.status == "effective",
            )
        )
    ).scalars().all()

    def _to_out(e: Experience) -> dict[str, Any]:
        return {
            "id": str(e.id),
            "code": e.code,
            "type": e.type,
            "title": e.title,
            "status": e.status,
            "due_date": e.due_date,
        }

    return OverviewOut(
        metrics={
            "effective_decisions": effective or 0,
            "open_actions": open_actions or 0,
            "total_experiences": total or 0,
            "total_meetings": meetings or 0,
        },
        attention_list=[_to_out(e) for e in attention],  # type: ignore[arg-type]
        pilots=[_to_out(e) for e in pilots],  # type: ignore[arg-type]
        decision_quotes=[_to_out(e) for e in quotes],  # type: ignore[arg-type]
    )


# --------------------------------------------------------------------- #
# Review queue (G2 threads suspended in interrupt)
# --------------------------------------------------------------------- #
@router.get("/projects/{pid}/review/queue")
async def review_queue(
    pid: str, session: AsyncSession = Depends(get_session)
) -> list[dict[str, Any]]:
    """Review queue = pending extractions = threads suspended in interrupt.

    Lazily starts a G2 thread per pending draft: the graph runs until it hits
    ``interrupt()`` (persisted by the checkpointer), so a verdict can resume
    the thread even after a restart.
    """
    pid = _parse_uuid(pid, "project id")
    rows = (
        await session.execute(
            select(Extraction)
            .join(Meeting, Meeting.id == Extraction.meeting_id)
            .where(Meeting.project_id == pid, Extraction.review_status == "pending")
            .order_by(Extraction.meeting_id)
        )
    ).scalars().all()

    items: list[dict[str, Any]] = []
    for ext in rows:
        thread_id = f"review-{ext.id}"
        if thread_id not in review_threads:
            draft = dict(ext.draft_json or {})
            draft.setdefault("type", "decision")
            draft.setdefault("title", "(untitled draft)")
            draft.setdefault("source", {})
            review_threads[thread_id] = {
                "project_id": pid,
                "meeting_id": str(ext.meeting_id),
                "extraction_id": str(ext.id),
                "draft": draft,
                "similar": [],
            }
            if thread_id not in getattr(review_queue, "_started", set()):
                started: set[str] = getattr(review_queue, "_started", set())
                g2 = build_review_graph().compile()
                try:
                    await g2.ainvoke(
                        {
                            "thread_id": thread_id,
                            "meeting_id": str(ext.meeting_id),
                            "project_id": pid,
                            "draft": draft,
                            "similar": [],
                            "suggestions": [],
                            "change_log": [],
                        },
                        config={"configurable": {"thread_id": thread_id}},
                        checkpointer=await get_checkpointer(),
                    )
                except Exception:  # noqa: BLE001 - queue listing must not fail
                    logger.exception("Failed to start review thread %s", thread_id)
                started.add(thread_id)
                review_queue._started = started  # type: ignore[attr-defined]
        st = review_threads[thread_id]
        if not st.get("resolved"):
            items.append(
                {"thread_id": thread_id, "draft": st["draft"], "similar": st.get("similar", [])}
            )
    return items


@router.post("/review/{token}/submit")
async def review_submit(
    token: str, payload: ReviewSubmit, session: AsyncSession = Depends(get_session)
) -> dict[str, Any]:
    """Resume the interrupted G2 thread with the reviewer's verdict.

    Runs ``review_graph.ainvoke(Command(resume=payload), thread)``: the graph
    decides promote vs reject; on promote we generate the code and persist via
    MemoryService (formal layer + change_log). The meeting flips to 'reviewed'
    when its extraction queue is empty.
    """
    st = review_threads.get(token)
    if st is None:
        raise HTTPException(status_code=404, detail="Review thread not found")
    if payload.decision == "reject" and not payload.reason:
        raise HTTPException(status_code=422, detail="Rejection requires a reason")

    # Execute the G2 graph tail: apply_decision -> promote | reject.
    g2 = build_review_graph().compile()
    checkpointer = await get_checkpointer()
    final = await g2.ainvoke(
        Command(resume=payload.model_dump(mode="json")),
        config={"configurable": {"thread_id": token}},
        checkpointer=checkpointer,
    )
    outcome = final.get("outcome", "rejected")

    result: dict[str, Any] = {}
    if outcome == "promoted":
        draft = st["draft"]
        if payload.decision == "accept_edited" and payload.edited is not None:
            draft = {
                **draft,
                "title": payload.edited.title,
                "description": payload.edited.description,
                "type": payload.edited.type,
                "acceptance_criteria": payload.edited.acceptance_criteria,
            }
        memory = MemoryService(session)
        code = await next_experience_code(session, draft["type"])
        exp = await memory.promote_draft(
            st["project_id"], draft, st.get("meeting_id"), payload.reviewer_id, code=code
        )
        await session.commit()
        result = {"experience_id": str(exp.id), "code": code}

    # When the meeting's review queue is empty, mark it reviewed.
    meeting_id = st.get("meeting_id")
    if meeting_id:
        remaining = await session.scalar(
            select(func.count())
            .select_from(Extraction)
            .where(Extraction.meeting_id == meeting_id, Extraction.review_status == "pending")
        )
        if not remaining:
            meeting = await session.get(Meeting, meeting_id)
            if meeting is not None:
                meeting.review_status = "reviewed"
            await session.commit()

    st["resolved"] = True
    st["outcome"] = outcome
    return {"outcome": outcome, **result}


# --------------------------------------------------------------------- #
# Briefing (G3) - markdown export
# --------------------------------------------------------------------- #
@router.post("/projects/{pid}/briefing")
async def briefing(
    pid: str, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    """Generate the pre-meeting briefing (markdown; docx/pdf in M2)."""
    await _ensure_project(session, pid)
    attention_rows = (
        await session.execute(
            select(Experience)
            .where(Experience.project_id == pid, Experience.status == "pending")
            .order_by(Experience.updated_at.desc())
            .limit(10)
        )
    ).scalars().all()
    attention = [
        {
            "code": e.code or "",
            "title": e.title,
            "source_meeting_id": str(e.source_meeting_id) if e.source_meeting_id else "",
        }
        for e in attention_rows
    ]
    open_actions_rows = (
        await session.execute(
            select(Experience, User)
            .outerjoin(User, User.id == Experience.owner_id)
            .where(
                Experience.project_id == pid,
                Experience.type == "action",
                Experience.status.in_(["pending", "in_progress"]),
            )
        )
    ).all()
    open_actions = [
        {
            "title": e.title,
            "owner_name": u.name if u else None,
            "due_date": e.due_date.isoformat() if e.due_date else None,
        }
        for e, u in open_actions_rows
    ]
    from eep.graphs.briefing import build_briefing_graph

    g3 = build_briefing_graph().compile()
    state = await g3.ainvoke(
        {"project_id": pid, "attention": attention, "open_actions": open_actions}
    )
    return {"briefing_markdown": state.get("briefing_markdown", ""), "format": "markdown"}


# --------------------------------------------------------------------- #
# Config hot reload (deploy doc 10.1: ConfigMap change -> reload)
# --------------------------------------------------------------------- #
@router.post("/internal/ai-config/reload")
async def reload_ai_config() -> dict[str, Any]:
    """Re-validate ai-providers.yaml and atomically swap the model factory."""
    global factory, semaphores
    cfg = load_ai_config()
    new_factory = ModelFactory(cfg)
    factory = new_factory
    semaphores = ProviderSemaphores(cfg)
    return {
        "reloaded": True,
        "providers": [p.name for p in cfg.providers],
        "breaker_state": new_factory.breaker_state(),
    }


# --------------------------------------------------------------------- #
# AI provider health (for Spring aggregation / "connected services" page)
# --------------------------------------------------------------------- #
@router.get("/admin/ai-providers/health")
async def ai_providers_health() -> list[dict[str, Any]]:
    """Probe all configured providers; 30s-cycle breaker state included."""
    from eep.ai_providers.health import probe

    cfg = load_ai_config()
    reports = []
    breaker_states = factory.breaker_state() if factory else {}
    for p in cfg.providers:
        report = await probe(p)
        report_dict = report.__dict__.copy()
        report_dict["breaker_state"] = breaker_states.get(p.name, "closed")
        report_dict["last_probe_at"] = datetime.now(UTC).isoformat()
        reports.append(report_dict)
    return reports
