"""MemoryService write-path tests (in-memory SQLite; no pgvector needed).

Author: Wang, Bing <colin2wang@gmail.com>
"""

import pytest
from sqlalchemy import func, select

from eep.db.models import ChangeLog, ExpMeeting, Experience
from eep.memory.service import MemoryService
from eep.seed import seed


async def test_promote_draft_writes_experience_evidence_and_changelog(session) -> None:
    await seed(session)
    await session.commit()
    memory = MemoryService(session)
    draft = {
        "type": "decision",
        "title": "新增试点场景：库存周转预测",
        "description": "11 月扩项讨论",
        "status": "pending",
        "source": {"span": {"start": 0, "end": 12, "quote": "库存周转预测"}},
    }
    exp = await memory.promote_draft(
        "00000000-0000-0000-0000-000000000001", draft, meeting_id=None, code="decision-107"
    )
    await session.commit()

    assert exp.code == "decision-107"
    n_evidence = await session.scalar(
        select(func.count()).select_from(ExpMeeting).where(ExpMeeting.exp_id == exp.id)
    )
    assert n_evidence == 0  # no meeting id -> no evidence row
    n_log = await session.scalar(
        select(func.count()).select_from(ChangeLog).where(ChangeLog.entity_id == exp.id)
    )
    assert n_log == 1  # "created" entry


async def test_promote_draft_prefers_edited_title(session) -> None:
    memory = MemoryService(session)
    draft = {
        "type": "action",
        "title": "原标题",
        "edited_title": "审核修正后的标题",
        "source": {},
    }
    exp = await memory.promote_draft("00000000-0000-0000-0000-000000000001", draft, meeting_id=None)
    assert exp.title == "审核修正后的标题"


async def test_patch_experience_writes_one_changelog_row_per_field(session) -> None:
    await seed(session)
    await session.commit()
    memory = MemoryService(session)
    exp = await session.scalar(select(Experience).where(Experience.code == "action-114"))
    out = await memory.patch_experience(
        exp.id, {"status": "in_progress", "title": exp.title}, actor_id=None
    )
    await session.commit()

    assert out.status == "in_progress"
    fields = (
        await session.execute(
            select(ChangeLog.field).where(ChangeLog.entity_id == exp.id, ChangeLog.field != "created")
        )
    ).scalars().all()
    assert fields == ["status"]  # unchanged field writes no row


async def test_patch_experience_skips_none_and_unknown_fields(session) -> None:
    await seed(session)
    await session.commit()
    memory = MemoryService(session)
    exp = await session.scalar(select(Experience).where(Experience.code == "action-114"))
    out = await memory.patch_experience(exp.id, {"nonexistent_field": "x", "description": None})
    assert out.description == "跟进客户管理层正式授权的审批流程，及时补充材料。"  # None ignored, not cleared
    assert not hasattr(out, "nonexistent_field")


async def test_expire_fact_sets_dual_timeline(session) -> None:
    await seed(session)
    await session.commit()
    memory = MemoryService(session)
    old = await session.scalar(select(Experience).where(Experience.code == "decision-102"))
    new = await session.scalar(select(Experience).where(Experience.code == "decision-106"))
    await memory.expire_fact(old.id, new.id)
    await session.commit()

    await session.refresh(old)
    assert old.t_invalid is not None
    assert str(old.superseded_by) == str(new.id)


async def test_retrieve_degrades_to_recency_without_embedding(session, pid) -> None:
    """No embedder configured/available -> formal-layer recency fallback."""
    await seed(session)
    await session.commit()
    memory = MemoryService(session)

    async def _no_embed(text: str) -> list[float] | None:
        return None

    memory.embed_query = _no_embed  # type: ignore[method-assign]
    hits = await memory.retrieve(pid, "试点", top_k=5)
    assert len(hits) == 5
    for h in hits:
        assert h["source_meeting_id"] or h["source_meeting_id"] is None
        assert "title" in h and "type" in h


async def test_retrieve_respects_type_filter(session, pid) -> None:
    await seed(session)
    await session.commit()
    memory = MemoryService(session)

    async def _no_embed(text: str) -> list[float] | None:
        return None

    memory.embed_query = _no_embed  # type: ignore[method-assign]
    # expand_edges=False: 1-hop expansion deliberately pulls in neighbors of
    # any type, so the pure type-filter path is tested without it.
    hits = await memory.retrieve(
        pid, "anything", exp_type="decision", top_k=100, expand_edges=False
    )
    assert len(hits) == 6
    assert all(h["type"] == "decision" for h in hits)


async def test_retrieve_excludes_invalidated_facts(session, pid) -> None:
    """Superseded decisions drop out of retrieval (dual timeline, 5.5)."""
    await seed(session)
    await session.commit()
    memory = MemoryService(session)

    async def _no_embed(text: str) -> list[float] | None:
        return None

    memory.embed_query = _no_embed  # type: ignore[method-assign]
    old = await session.scalar(select(Experience).where(Experience.code == "decision-102"))
    new = await session.scalar(select(Experience).where(Experience.code == "decision-106"))
    await memory.expire_fact(old.id, new.id)
    await session.commit()

    hits = await memory.retrieve(
        pid, "anything", exp_type="decision", top_k=100, expand_edges=False
    )
    ids = {h["id"] for h in hits}
    assert str(old.id) not in ids
    assert str(new.id) in ids
