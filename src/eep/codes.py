"""Experience code generator: type-prefixed sequential codes (action-114 style).

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from eep.db.models import Experience

TYPE_PREFIX = {
    "question": "question",
    "hypothesis": "hypothesis",
    "experiment": "experiment",
    "decision": "decision",
    "action": "action",
}


async def next_experience_code(session: AsyncSession, exp_type: str) -> str:
    """Generate the next code for the type, e.g. ``action-115``.

    Counts existing rows of the type and appends one. A unique-violation
    retry is handled by the caller committing under the session transaction;
    for Phase 1 volume this counter approach is sufficient.
    """
    prefix = TYPE_PREFIX.get(exp_type, exp_type)
    count = await session.scalar(
        select(func.count())
        .select_from(Experience)
        .where(Experience.type == exp_type, Experience.code.is_not(None))
    )
    return f"{prefix}-{(count or 0) + 1}"


__all__ = ["next_experience_code"]
