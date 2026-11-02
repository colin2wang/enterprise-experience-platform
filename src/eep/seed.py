"""Demo seed data matching the design document (chapter 3.2 sample calibration).

Populates one project ("示范项目") with 5 meetings, 16 experiences
(1 question + 0 hypothesis + 2 experiments + 6 decisions + 7 actions),
evidence links, evolution-chain relations and a starter change log — so the
web UI renders the reference screens from the product design immediately.

Idempotent: re-running skips seeding when the project already exists.

Usage:
    python -m eep.seed            # seed the configured database
    python -m eep.seed --force    # wipe the demo project first, then reseed

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eep.config import Settings
from eep.db import base as db_base
from eep.db.models import (
    ChangeLog,
    ExpMeeting,
    Experience,
    Meeting,
    Project,
    Relation,
    User,
)

logger = logging.getLogger("eep.seed")

PROJECT_NAME = "Demo Project"

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
USERS = ["Alice Johnson", "Brian Miller", "Clara Schmidt", "David Thompson"]

# ---------------------------------------------------------------------------
# Meetings — 5 sessions, transcript-prefixed titles, all reviewed & ingested
# ---------------------------------------------------------------------------
MEETINGS = [
    {
        "title": "Transcript_2026-10-12_Internal Tools Pilot Kickoff",
        "meet_date": date(2026, 10, 12),
        "participants": ["Alice Johnson", "Brian Miller", "Clara Schmidt"],
        "summary": "Confirmed the pilot kickoff for the internal tools project. First candidate scenarios: knowledge-base Q&A and smart ticket routing. Agreed on points of contact and a weekly cadence.",
        "discussion": "Clara: The support team wastes the most time hunting through multiple doc spaces for answers; new hires ramp up slowly.\n"
                      "Alice: Ticket routing today is manual triage by title, and misroutes are frequent.\n"
                      "Brian: Suggest we focus a feasibility assessment on these two scenarios and draft an initial proposal next week.",
    },
    {
        "title": "Transcript_2026-10-17_Scenario Priority Review",
        "meet_date": date(2026, 10, 17),
        "participants": ["Alice Johnson", "Brian Miller", "David Thompson"],
        "summary": "After reviewing technical feasibility of both scenarios, confirmed the first pilot scope as knowledge-base Q&A and smart ticket routing.",
        "discussion": "Brian: The existing knowledge-base articles are well structured, so Q&A can go first.\n"
                      "Alice: Smart routing needs labeled historical tickets; we should start data prep in parallel.\n"
                      "David: Decision — first pilot scenarios confirmed as knowledge-base Q&A and smart ticket routing.",
    },
    {
        "title": "Transcript_2026-10-25_Data Ingestion Design Review",
        "meet_date": date(2026, 10, 25),
        "participants": ["Clara Schmidt", "David Thompson", "Alice Johnson"],
        "summary": "Reviewed the data ingestion plan: knowledge-base docs sync via API; historical tickets exported to CSV by the client and bulk-imported. Acceptance criteria agreed.",
        "discussion": "Clara: The knowledge-base system has an open API; we can sync the full category tree.\n"
                      "David: Historical tickets live in the ticketing system; the client needs to export a first CSV cut.\n"
                      "Alice: Confirmed — the client owns the ticket export, first version due by end of October.",
    },
    {
        "title": "Transcript_2026-11-01_Pilot Scope and Milestone Alignment",
        "meet_date": date(2026, 11, 1),
        "participants": ["Alice Johnson", "Brian Miller", "Clara Schmidt", "David Thompson"],
        "summary": "Aligned pilot milestones: Q&A prototype validation by mid-November, historical ticket import done by end of November. Inconsistent ticket taxonomy identified as the top risk.",
        "discussion": "Brian: Plan is to finish the Q&A prototype validation by November 15.\n"
                      "Clara: Ticket taxonomy differs across product lines — that is the biggest risk.\n"
                      "Alice: Next step is presenting the pilot plan to the client's management for formal sign-off.",
    },
    {
        "title": "Transcript_2026-11-02_Pilot Proposal Review Retrospective",
        "meet_date": date(2026, 11, 2),
        "participants": ["Alice Johnson", "David Thompson"],
        "summary": "Pilot proposal presented to the client's management; approval is in process. Follow-ups: track the approval and prepare supplementary material.",
        "discussion": "Alice: The proposal landed well with management overall; formal authorization is still in the approval pipeline.\n"
                      "David: To-do — the client submits supplementary material with feedback; the project decision process moves forward.",
    },
]

# ---------------------------------------------------------------------------
# Experiences — 16 total: 1 question + 2 experiments + 6 decisions + 7 actions
# Codes: question-87 / experiment-91..92 / decision-101..106 / action-108..114
# (index into MEETINGS = first-record meeting)
# ---------------------------------------------------------------------------
EXPERIENCES = [
    # question x1
    {
        "code": "question-87", "type": "question", "m": 0,
        "title": "How do we unify the ticket taxonomy across product lines?",
        "description": "Each product line uses a different ticket classification scheme, so routing rules cannot be reused; we need a unified taxonomy first.",
        "status": "in_progress", "owner": "Brian Miller",
    },
    # experiment x2
    {
        "code": "experiment-91", "type": "experiment", "m": 0,
        "title": "Knowledge-base Q&A prototype validation",
        "description": "Build a Q&A prototype on documents synced via the knowledge-base API and validate answer accuracy and retrieval efficiency.",
        "status": "planned", "owner": "Brian Miller", "due": date(2026, 11, 15),
    },
    {
        "code": "experiment-92", "type": "experiment", "m": 2,
        "title": "Historical ticket bulk-import validation",
        "description": "Bulk-import the client-exported historical ticket CSV into the platform and validate field mapping and data quality.",
        "status": "planned", "owner": "Clara Schmidt", "due": date(2026, 11, 30),
    },
    # decision x6
    {
        "code": "decision-101", "type": "decision", "m": 0,
        "title": "Demo project pilot officially started",
        "description": "Both sides confirmed the pilot kickoff, with named points of contact and a weekly sync cadence.",
        "status": "effective", "owner": "Alice Johnson",
    },
    {
        "code": "decision-102", "type": "decision", "m": 1,
        "title": "First pilot scenarios confirmed as knowledge-base Q&A and smart ticket routing",
        "description": "After the feasibility review, the first pilot locks in two scenarios: knowledge-base Q&A (first) and smart ticket routing (data prep in parallel).",
        "status": "effective", "owner": "Alice Johnson",
    },
    {
        "code": "decision-103", "type": "decision", "m": 2,
        "title": "Knowledge-base documents ingested via API",
        "description": "No manual exports; knowledge-base documents are synced through the system's open API along the category tree.",
        "status": "effective", "owner": "Clara Schmidt",
    },
    {
        "code": "decision-104", "type": "decision", "m": 2,
        "title": "Historical tickets exported by the client and bulk-imported",
        "description": "Historical tickets remain in the client's ticketing system; the client exports a first CSV cut and the platform bulk-imports it.",
        "status": "effective", "owner": "Clara Schmidt",
    },
    {
        "code": "decision-105", "type": "decision", "m": 3,
        "title": "Pilot milestones set: mid-November prototype, end-November ticket import",
        "description": "Aligned milestones: Q&A prototype validation by November 15; historical ticket import by end of November.",
        "status": "effective", "owner": "Alice Johnson",
    },
    {
        "code": "decision-106", "type": "decision", "m": 4,
        "title": "Pilot plan verbally endorsed by management; formal approval in process",
        "description": "After the proposal review, management endorsed the pilot overall and formal authorization entered the approval pipeline.",
        "status": "effective", "owner": "Alice Johnson",
    },
    # action x7
    {
        "code": "action-108", "type": "action", "m": 0,
        "title": "Draft feasibility proposal for both scenarios",
        "description": "Produce an initial feasibility proposal covering knowledge-base Q&A and smart ticket routing.",
        "status": "done", "owner": "Brian Miller", "due": date(2026, 10, 19),
        "acceptance": "Proposal document completed and jointly reviewed.",
    },
    {
        "code": "action-109", "type": "action", "m": 1,
        "title": "Document knowledge-base API data dictionary",
        "description": "Align API fields with the client's knowledge-base vendor and produce a data dictionary.",
        "status": "done", "owner": "Clara Schmidt", "due": date(2026, 10, 26),
        "acceptance": "Data dictionary confirmed by both sides.",
    },
    {
        "code": "action-110", "type": "action", "m": 2,
        "title": "Client exports first cut of historical tickets",
        "description": "Export historical tickets per product line to the platform's CSV field template.",
        "status": "in_progress", "owner": "Alice Johnson", "due": date(2026, 11, 7),
        "acceptance": "First CSV cut submitted with field completeness ≥ 90%.",
    },
    {
        "code": "action-111", "type": "action", "m": 3,
        "title": "Complete knowledge-base Q&A prototype validation",
        "description": "Run prototype validation on synced documents and produce a validation report.",
        "status": "in_progress", "owner": "Brian Miller", "due": date(2026, 11, 15),
        "acceptance": "Validation report shows answer accuracy ≥ 95%.",
    },
    {
        "code": "action-112", "type": "action", "m": 3,
        "title": "Draft unified ticket taxonomy standard",
        "description": "Consolidate classification differences across product lines into a unified taxonomy draft.",
        "status": "in_progress", "owner": "Brian Miller", "due": date(2026, 11, 20),
        "acceptance": "Taxonomy draft reviewed by the client's support department.",
    },
    {
        "code": "action-113", "type": "action", "m": 3,
        "title": "Present pilot proposal to client management",
        "description": "Prepare the presentation deck and brief management on the pilot plan.",
        "status": "done", "owner": "Alice Johnson", "due": date(2026, 11, 1),
        "acceptance": "Presentation delivered and management feedback received.",
    },
    {
        # The reference sample from the design doc / screenshots (图2).
        "code": "action-114", "type": "action", "m": 4,
        "title": "Follow up on pilot authorization approval",
        "description": "Track the formal-authorization approval with the client's management and supply supplementary material promptly.",
        "status": "pending", "owner": "Alice Johnson", "due": None,  # 待明确
        "acceptance": "Client submits supplementary material with feedback; the project decision process moves forward.",
    },
]

# ---------------------------------------------------------------------------
# Evolution-chain relations (from_exp, to_exp, rel_type) — by code
# ---------------------------------------------------------------------------
RELATIONS = [
    ("question-87", "decision-105", "supports"),
    ("question-87", "action-112", "evolves"),
    ("decision-101", "decision-102", "evolves"),
    ("decision-102", "experiment-91", "grounds"),
    ("decision-102", "experiment-92", "grounds"),
    ("experiment-91", "decision-103", "supports"),
    ("decision-103", "action-109", "grounds"),
    ("decision-104", "experiment-92", "grounds"),
    ("decision-104", "action-110", "grounds"),
    ("decision-105", "action-111", "grounds"),
    ("decision-105", "action-112", "grounds"),
    ("action-113", "decision-106", "supports"),
    ("decision-106", "action-114", "grounds"),
    ("action-113", "action-114", "evolves"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _project_exists(session: AsyncSession) -> Project | None:
    return await session.scalar(select(Project).where(Project.name == PROJECT_NAME))


async def _wipe(session: AsyncSession, project: Project) -> None:
    """Delete the demo project and everything hanging off it."""
    exp_ids = (
        await session.scalars(
            select(Experience.id).where(Experience.project_id == project.id)
        )
    ).all()
    if exp_ids:
        await session.execute(delete(Relation).where(Relation.from_exp.in_(exp_ids)))
        await session.execute(delete(ExpMeeting).where(ExpMeeting.exp_id.in_(exp_ids)))
    await session.execute(
        delete(Meeting).where(Meeting.project_id == project.id)
    )
    await session.execute(delete(Experience).where(Experience.project_id == project.id))
    await session.execute(delete(Project).where(Project.id == project.id))
    await session.flush()


async def seed(session: AsyncSession, *, force: bool = False) -> dict[str, int]:
    """Seed the demo dataset; returns row counts.

    Args:
        session: Active async session (caller commits).
        force: Remove an existing demo project first, then reseed.
    """
    project = await _project_exists(session)
    if project is not None and not force:
        logger.info("Project %r already seeded — skipping (use --force to reseed)", PROJECT_NAME)
        counts = await _counts(session)
        return counts
    if project is not None:
        await _wipe(session, project)

    # Fixed demo UUID so the frontend default project id matches out of the box.
    project = Project(id=uuid.UUID("00000000-0000-0000-0000-000000000001"), name=PROJECT_NAME)
    session.add(project)

    users = {name: User(id=uuid.uuid4(), name=name) for name in USERS}
    session.add_all(users.values())

    meetings = [
        Meeting(
            id=uuid.uuid4(),
            project_id=project.id,
            title=m["title"],
            meet_date=m["meet_date"],
            participants=m["participants"],
            source_type="transcript",
            summary=m["summary"],
            discussion=m["discussion"],
            review_status="reviewed",
            exp_stat_cache={},
        )
        for m in MEETINGS
    ]
    session.add_all(meetings)

    experiences: list[Experience] = []
    for e in EXPERIENCES:
        meeting = meetings[e["m"]]
        exp = Experience(
            id=uuid.uuid4(),
            project_id=project.id,
            code=e["code"],
            type=e["type"],
            title=e["title"],
            description=e["description"],
            status=e["status"],
            owner_id=users[e["owner"]].id if e.get("owner") else None,
            due_date=e.get("due"),
            acceptance_criteria=e.get("acceptance"),
            source_meeting_id=meeting.id,
            source_span={"quote": e["description"], "start": 0, "end": len(e["description"])},
            t_event=meeting.meet_date,
        )
        experiences.append(exp)
        session.add(exp)
        session.add(
            ExpMeeting(
                exp_id=exp.id,
                meeting_id=meeting.id,
                evidence_span={"quote": e["description"], "start": 0, "end": len(e["description"])},
                is_first_record=True,
            )
        )

    by_code = {e.code: e for e in experiences}
    for from_code, to_code, rel_type in RELATIONS:
        session.add(
            Relation(
                id=uuid.uuid4(),
                from_exp=by_code[from_code].id,
                to_exp=by_code[to_code].id,
                rel_type=rel_type,
                origin="manual",
                confidence=1.0,
                meeting_id=by_code[to_code].source_meeting_id,
            )
        )

    # Refresh per-meeting experience statistics cache (B1: 沉淀统计).
    for meeting in meetings:
        linked = [e for e in experiences if e.source_meeting_id == meeting.id]
        by_type: dict[str, int] = {}
        for e in linked:
            by_type[e.type] = by_type.get(e.type, 0) + 1
        meeting.exp_stat_cache = {
            "total": len(linked),
            "first_records": len(linked),
            "type_distribution": by_type,
        }

    session.add(
        ChangeLog(
            entity_type="project",
            entity_id=project.id,
            field="seed",
            old_value=None,
            new_value=f"demo dataset: {len(meetings)} meetings, {len(experiences)} experiences",
            at=_now(),
            source="ui",
        )
    )
    await session.flush()
    return await _counts(session)


async def _counts(session: AsyncSession) -> dict[str, int]:
    meetings_n = await session.scalar(
        select(func.count()).select_from(Meeting).join(Project, Meeting.project_id == Project.id)
        .where(Project.name == PROJECT_NAME)
    )
    exps_n = await session.scalar(
        select(func.count()).select_from(Experience).join(Project, Experience.project_id == Project.id)
        .where(Project.name == PROJECT_NAME)
    )
    return {"meetings": meetings_n or 0, "experiences": exps_n or 0}


async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the EEP demo dataset")
    parser.add_argument("--force", action="store_true", help="wipe and reseed the demo project")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
    db_base.init_engine(Settings().database_url)
    from eep.main import _auto_init_database  # sqlite auto-init, like the app

    await _auto_init_database(Settings().database_url)

    factory = db_base.session_factory()
    async with factory() as session:
        counts = await seed(session, force=args.force)
        await session.commit()
    logger.info("Seeded %s: %s", PROJECT_NAME, counts)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(asyncio.run(main()))
