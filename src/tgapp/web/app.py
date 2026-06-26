from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tgapp.config import AppConfig
from tgapp.infrastructure.storage import SessionStorage
from tgapp.web.routes import router


def create_app(config: AppConfig | None = None) -> FastAPI:
    app_config = config or AppConfig.from_env()
    storage = SessionStorage(app_config.session_dir)
    storage.ensure()

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
