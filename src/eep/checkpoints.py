"""Checkpointer wiring: persistent G2 review state across restarts.

Uses AsyncPostgresSaver against the business database when reachable
(review threads must survive restarts for days); falls back to an in-memory
saver for dev/test runs without Postgres so the graphs still execute.

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver

from eep.config import Settings

logger = logging.getLogger(__name__)

_checkpointer: BaseCheckpointSaver | None = None


async def get_checkpointer() -> BaseCheckpointSaver:
    """Return the global checkpointer, creating it on first use.

    Postgres is the production choice (same engine as the business DB);
    MemorySaver covers smoke tests and offline development.
    """
    global _checkpointer
    if _checkpointer is not None:
        return _checkpointer
    settings = Settings()
    # SQLite dev default: a file-backed saver so review threads (interrupt
    # state) survive restarts just like they do with Postgres in production.
    if settings.database_url.startswith("sqlite"):
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            path = "eep.checkpoints.sqlite3"
            saver = AsyncSqliteSaver.from_conn_string(path)
            cm = await saver.__aenter__() if hasattr(saver, "__aenter__") else saver
            await cm.setup()  # create checkpoint tables
            _checkpointer = cm
            logger.info("Checkpointer: AsyncSqliteSaver (%s)", path)
            return _checkpointer
        except Exception as exc:  # noqa: BLE001 - dev fallback
            from langgraph.checkpoint.memory import InMemorySaver

            _checkpointer = InMemorySaver()
            logger.warning("SQLite checkpointer unavailable (%s); using InMemorySaver", exc)
            return _checkpointer
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        # AsyncPostgresSaver expects a psycopg-compatible connection string.
        dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
        saver = AsyncPostgresSaver.from_conn_string(dsn)
        cm = await saver.__aenter__() if hasattr(saver, "__aenter__") else saver
        await cm.setup()  # create checkpoint tables
        _checkpointer = cm
        logger.info("Checkpointer: AsyncPostgresSaver")
    except Exception as exc:  # noqa: BLE001 - dev fallback
        from langgraph.checkpoint.memory import InMemorySaver

        _checkpointer = InMemorySaver()
        logger.warning("Postgres checkpointer unavailable (%s); using InMemorySaver", exc)
    return _checkpointer
