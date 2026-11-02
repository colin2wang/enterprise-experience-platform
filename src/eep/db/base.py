"""Async SQLAlchemy engine/session setup.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from eep.config import Settings

logger = logging.getLogger("eep.db")

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def connection_target(database_url: str) -> str:
    """Extract a readable ``host:port/db`` target from a database URL."""
    m = re.search(r"@([^/:?]+)(?::(\d+))?/([^/?]+)", database_url)
    if m:
        host, port, db = m.group(1), m.group(2) or "5432", m.group(3)
        return f"{host}:{port}/{db}"
    return database_url.split("@")[-1]  # credentials-stripped fallback


def init_engine(database_url: str | None = None) -> AsyncEngine:
    """Create (or replace) the global async engine.

    Args:
        database_url: Override URL; defaults to ``Settings.database_url``.
    """
    global _engine, _session_factory
    url = database_url or Settings().database_url
    _engine = create_async_engine(url, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global session factory, initializing the engine lazily."""
    if _session_factory is None:
        init_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session per request.

    On connection failure the remote address is logged explicitly so the
    operator can see which host:port refused the connection.
    """
    factory = session_factory()
    try:
        async with factory() as session:
            yield session
    except (OperationalError, OSError, ConnectionError):
        # asyncpg raises a bare ConnectionRefusedError (an OSError) that does
        # not pass through SQLAlchemy's DBAPI wrapping, so catch both.
        url = _engine.url.render_as_string(hide_password=True) if _engine else Settings().database_url
        logger.error(
            "Database connection failed -> remote address: %s (is PostgreSQL running?)",
            connection_target(url),
        )
        raise
