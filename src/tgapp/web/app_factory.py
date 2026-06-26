from __future__ import annotations

from dash import Dash  # pyright: ignore[reportMissingImports]

from tgapp.config import AppConfig
from tgapp.infrastructure.storage import SessionStorage
from tgapp.web.callbacks import register_callbacks
from tgapp.web.layout import create_layout


def create_app(config: AppConfig) -> Dash:
    session_storage = SessionStorage(config.session_dir)
    session_storage.ensure()

    app = Dash(
        __name__,
        title="tg.app Migration Skeleton",
        requests_pathname_prefix=config.base_path,
        routes_pathname_prefix=config.base_path,
        suppress_callback_exceptions=True,
    )
    app.layout = create_layout()
    app.server.config["TGAPP_SESSION_DIR"] = str(session_storage.root)
    register_callbacks(app)
    return app
