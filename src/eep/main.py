"""FastAPI application entrypoint.

Wires config, model factory, DB engine and all routers.
Run: uvicorn eep.main:app --host 0.0.0.0 --port 8100

Author: Wang, Bing <colin2wang@gmail.com>
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from eep.ai_providers import ModelFactory, ProviderSemaphores
from eep.config import load_ai_config, load_app_config
from eep.db.base import init_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eep")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: init engine + provider singletons + auto-init DB."""
    settings = load_app_config()  # env EEP_* > eep.yml > defaults
    init_engine(settings.database_url)
    await _auto_init_database(settings.database_url)
    cfg = load_ai_config(settings.ai_providers_path)
    app.state.settings = settings
    app.state.ai_config = cfg
    app.state.model_factory = ModelFactory(cfg)
    app.state.provider_semaphores = ProviderSemaphores(cfg)

    from eep.api import routes

    routes.factory = app.state.model_factory
    routes.semaphores = app.state.provider_semaphores
    logger.info("EEP AI service started with %d providers", len(cfg.providers))
    logger.info("Database:    %s", settings.database_url.split("@")[-1])
    logger.info("Web UI:      http://%s:%d/web/", settings.host, settings.port)
    logger.info("API docs:    http://%s:%d/docs", settings.host, settings.port)
    logger.info("Health:      http://%s:%d/healthz", settings.host, settings.port)
    yield


async def _auto_init_database(database_url: str) -> None:
    """Create all tables automatically on SQLite (zero-setup default).

    PostgreSQL schemas come from migrations/001_schema.sql instead, so only
    the sqlite dialect triggers the ORM create_all path here.
    """
    if not database_url.startswith("sqlite"):
        return
    from sqlalchemy.ext.asyncio import create_async_engine

    from eep.db.models import Base

    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()
    logger.info("SQLite database auto-initialized (all tables created)")


app = FastAPI(
    title="EEP AI Pipeline Service",
    version="0.1.0",
    lifespan=lifespan,
)

from eep.api.experiences import router as experiences_router  # noqa: E402
from eep.api.routes import router as core_router  # noqa: E402

app.include_router(core_router, prefix="/v1")
app.include_router(experiences_router, prefix="/v1")

# Serve the frontend SPA at /web.
app.mount("/web", StaticFiles(directory="web", html=True), name="web")


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect the site root to the web UI."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/web/")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    settings = load_app_config()
    uvicorn.run(app, host=settings.host, port=settings.port)
