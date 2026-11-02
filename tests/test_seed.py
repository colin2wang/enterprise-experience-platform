"""Seed script tests (in-memory SQLite; no pgvector needed).

Author: Wang, Bing <colin2wang@gmail.com>
"""

from sqlalchemy import func, select

from eep.db.models import ExpMeeting, Experience, Meeting, Project, Relation
from eep.seed import PROJECT_NAME, RELATIONS, seed


async def test_seed_creates_design_doc_sample(session) -> None:
    """16 experiences = 1+0+2+6+7 across 5 meetings, per design doc 3.2."""
    counts = await seed(session)
    await session.commit()

    assert counts == {"meetings": 5, "experiences": 16}
    assert await session.scalar(select(func.count()).select_from(Project)) == 1

    by_type = dict(
        (t, n)
        for t, n in (
            await session.execute(
                select(Experience.type, func.count()).group_by(Experience.type)
            )
        ).all()
    )
    assert by_type.get("question") == 1
    assert by_type.get("hypothesis") is None  # no hypothesis rows exist
    assert by_type.get("experiment") == 2
    assert by_type.get("decision") == 6
    assert by_type.get("action") == 7


async def test_seed_is_idempotent(session) -> None:
    await seed(session)
    await session.commit()
    counts = await seed(session)  # second run skips
    await session.commit()
    assert counts == {"meetings": 5, "experiences": 16}
    assert await session.scalar(select(func.count()).select_from(Meeting)) == 5


async def test_force_reseeds_without_duplicates(session) -> None:
    await seed(session)
    await session.commit()
    counts = await seed(session, force=True)
    await session.commit()
    assert counts == {"meetings": 5, "experiences": 16}
    assert await session.scalar(select(func.count()).select_from(Meeting)) == 5


async def test_action_114_reference_sample(session) -> None:
    """The design-doc / screenshot reference sample (图2)."""
    await seed(session)
    await session.commit()
    exp = await session.scalar(
        select(Experience).where(Experience.code == "action-114")
    )
    assert exp is not None
    assert exp.owner_id is not None          # 黄滔
    assert exp.due_date is None              # 待明确
    assert "客户方提交材料给出反馈" in (exp.acceptance_criteria or "")


async def test_evidence_links_and_relations(session) -> None:
    await seed(session)
    await session.commit()
    n_links = await session.scalar(select(func.count()).select_from(ExpMeeting))
    n_rels = await session.scalar(select(func.count()).select_from(Relation))
    assert n_links == 16                      # every experience has first-record evidence
    assert n_rels == len(RELATIONS)
