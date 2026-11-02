"""Experience library API route tests (in-memory SQLite; handlers called directly).

Author: Wang, Bing <colin2wang@gmail.com>
"""

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from eep.api.experiences import (
    chain_topics,
    claim_experience,
    experience_chain,
    experience_detail,
    list_experiences,
    patch_experience,
)
from eep.db.models import User
from eep.schemas import ExperiencePatch


async def test_list_experiences_filters_by_type(session, pid) -> None:
    actions = await list_experiences(pid, type="action", status=None, owner=None, q=None, sort="-updated", session=session)
    assert len(actions) == 7
    assert all(a.type == "action" for a in actions)


async def test_list_experiences_search_matches_title(session, pid) -> None:
    hits = await list_experiences(pid, type=None, status=None, owner=None, q="授权", sort="-updated", session=session)
    assert {h.code for h in hits} == {"decision-106", "action-114"}


async def test_list_experiences_owner_filter_by_id(session, pid) -> None:
    owner_id = str((await session.execute(select(User.id).where(User.name == "黄滔"))).scalars().first())
    hits = await list_experiences(pid, type=None, status=None, owner=owner_id, q=None, sort="-updated", session=session)
    assert len(hits) == 7
    assert all(h.owner_name == "黄滔" for h in hits)


async def test_detail_not_found_raises_404(session) -> None:
    with pytest.raises(HTTPException) as exc:
        await experience_detail("00000000-0000-0000-0000-000000000001", session=session)
    assert exc.value.status_code == 404


async def test_detail_carries_owner_name(session, pid) -> None:
    actions = await list_experiences(pid, type="action", status=None, owner=None, q=None, sort="-updated", session=session)
    detail = await experience_detail(actions[0].id, session=session)
    assert detail.owner_name in {"黄滔", "李文静", "张启明", "陈晓芸"}


async def test_patch_writes_change_log(session, pid) -> None:
    from sqlalchemy import func

    from eep.db.models import ChangeLog

    actions = await list_experiences(pid, type="action", status=None, owner=None, q=None, sort="-updated", session=session)
    target = next(a for a in actions if a.code == "action-114")
    out = await patch_experience(target.id, ExperiencePatch(status="in_progress"), session=session)
    assert out.status == "in_progress"
    n = await session.scalar(
        select(func.count())
        .select_from(ChangeLog)
        .where(ChangeLog.entity_id == target.id, ChangeLog.field == "status")
    )
    assert n == 1


async def test_claim_assigns_owner(session, pid) -> None:
    actions = await list_experiences(pid, type="action", status=None, owner=None, q=None, sort="-updated", session=session)
    new_owner = str(await session.scalar(select(User.id).limit(1)))
    out = await claim_experience(actions[0].id, new_owner, session=session)
    assert out.owner_id == new_owner


async def test_chain_returns_five_swimlanes(session, pid) -> None:
    actions = await list_experiences(pid, type="action", status=None, owner=None, q=None, sort="-updated", session=session)
    target = next(a for a in actions if a.code == "action-114")
    chain = await experience_chain(target.id, session=session)
    assert len(chain.lanes) == 5
    assert {lane.type for lane in chain.lanes} == {"question", "hypothesis", "experiment", "decision", "action"}


async def test_chain_topics_lists_related(session, pid) -> None:
    topics = await chain_topics(pid, q="试点", session=session)
    assert len(topics) > 0
    assert all(t["meeting_count"] >= 1 and t["relation_count"] >= 0 for t in topics)
