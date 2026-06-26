from __future__ import annotations

from dash import Dash, Input, Output, State, dcc  # pyright: ignore[reportMissingImports]

from tgapp.application.use_cases import export_session_archive
from tgapp.infrastructure.storage import SessionStorage


def _storage_from_app(app: Dash) -> SessionStorage:
    return SessionStorage(app.server.config["TGAPP_SESSION_DIR"])


def register_export_callbacks(app: Dash) -> None:
    storage = _storage_from_app(app)

    @app.callback(
        Output("download-plot", "data"),
        Input("download-plot-button", "n_clicks"),
        State("session-store", "data"),
        prevent_initial_call=True,
    )
    def export_plot(_: int, session_data: dict[str, object]):
        session_id = session_data.get("session_id") if isinstance(session_data, dict) else None
        if not isinstance(session_id, str) or not session_id:
            return dcc.send_string("No plot data available\n", "plot-data.csv")
        plot_path = storage.raw_plot_path(session_id)
        if not plot_path.exists():
            return dcc.send_string("No plot data available\n", "plot-data.csv")
        return dcc.send_file(str(plot_path))

    @app.callback(
        Output("download-session", "data"),
        Input("download-session-button", "n_clicks"),
        State("session-store", "data"),
        prevent_initial_call=True,
    )
    def export_session(_: int, session_data: dict[str, object]):
        archive_path = export_session_archive(storage, session_data)
        if archive_path is None:
            return dcc.send_string("No session available\n", "empty-session.tg")
        return dcc.send_file(str(archive_path))
