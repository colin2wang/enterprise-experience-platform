"""Experience code generator tests (in-memory SQLite; no pgvector needed).

Author: Wang, Bing <colin2wang@gmail.com>
"""

from uuid import uuid4

from eep.codes import next_experience_code
from eep.db.models import Experience


def _exp(exp_type: str, code: str) -> Experience:
    return Experience(project_id=uuid4(), type=exp_type, title="t", code=code)


async def test_first_code(session) -> None:
    assert await next_experience_code(session, "action") == "action-1"


async def test_sequence_increments(session) -> None:
    session.add(_exp("action", "action-1"))
    session.add(_exp("action", "action-2"))
    await session.flush()
    assert await next_experience_code(session, "action") == "action-3"


async def test_types_are_independent(session) -> None:
    session.add(_exp("decision", "decision-1"))
    await session.flush()
    assert await next_experience_code(session, "decision") == "decision-2"
    assert await next_experience_code(session, "question") == "question-1"
