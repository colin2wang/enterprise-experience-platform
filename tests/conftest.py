"""Global pytest fixtures: in-memory SQLite session + seeded project id.

Shared by all test packages (test_api / test_memory / test_seed, ...).

Author: Wang, Bing <colin2wang@gmail.com>
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from eep.db.models import Base, Project


@pytest.fixture()
async def session():
    """Fresh in-memory SQLite session with all tables created (no pgvector)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture()
async def pid(session) -> str:
    """Seed the demo dataset and return the project id."""
    from eep.seed import seed

    await seed(session)
    await session.commit()
    return str(await session.scalar(select(Project.id)))
