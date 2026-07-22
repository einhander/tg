from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tgapp.config import AppConfig
from tgapp.infrastructure.storage import SessionStorage
from tgapp.web.routes import router

logger = logging.getLogger(__name__)


def _run_session_cleanup(storage: SessionStorage, ttl_seconds: int) -> None:
    """Remove expired sessions. Called once at startup."""
    try:
        removed = storage.cleanup_expired(ttl_seconds=ttl_seconds)
        if removed:
            logger.info("Session cleanup: removed %d expired sessions", removed)
    except Exception:
        logger.warning("Session cleanup failed (non-fatal)", exc_info=True)


def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or AppConfig.from_env()
    storage = SessionStorage(app_config.session_dir)
    storage.ensure()

    # PLAN_AUDIT §17.3: cleanup expired sessions at startup
    _run_session_cleanup(storage, app_config.session_ttl)

    app = FastAPI(title="tg.app Migration Skeleton", root_path=app_config.base_path)
    app.state.config = app_config
    app.state.storage = storage

    templates_dir = Path(__file__).resolve().parent / "templates"
    app.state.templates = Jinja2Templates(directory=str(templates_dir))

    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.include_router(router)
    return app


app = create_app()
