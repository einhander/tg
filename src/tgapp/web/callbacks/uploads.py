from __future__ import annotations

from dataclasses import asdict

from dash import Dash, Input, Output, State, no_update  # pyright: ignore[reportMissingImports]

from tgapp.application.dto import UploadPayload
from tgapp.application.use_cases import create_session, import_saved_session, load_correction, load_thermograms
from tgapp.infrastructure.storage import SessionStorage


def _storage_from_app(app: Dash) -> SessionStorage:
    return SessionStorage(app.server.config["TGAPP_SESSION_DIR"])


def register_upload_callbacks(app: Dash) -> None:
    storage = _storage_from_app(app)

    @app.callback(Output("session-store", "data"), Input("url", "pathname"), prevent_initial_call=False)
    def ensure_session(_: str | None):
        return asdict(create_session(storage))

    @app.callback(
        Output("session-store", "data", allow_duplicate=True),
        Output("upload-status", "children"),
        Input("upload-thermograms", "contents"),
        State("upload-thermograms", "filename"),
        State("upload-thermograms", "type"),
        State("session-store", "data"),
        prevent_initial_call=True,
    )
    def handle_thermogram_upload(contents: list[str] | None, filenames: list[str] | None, content_types: list[str] | None, session_data: dict[str, object]):
        if not contents:
            return no_update, "No thermogram files uploaded."
        uploads = [UploadPayload(filename=(filenames or [None])[index], content_type=(content_types or [None])[index], content=content) for index, content in enumerate(contents)]
        state = load_thermograms(storage, session_data, uploads)
        return asdict(state), f"Loaded {len(uploads)} thermogram file(s)."

    @app.callback(
        Output("session-store", "data", allow_duplicate=True),
        Output("upload-status", "children", allow_duplicate=True),
        Input("upload-correction", "contents"),
        State("upload-correction", "filename"),
        State("upload-correction", "type"),
        State("session-store", "data"),
        prevent_initial_call=True,
    )
    def handle_correction_upload(contents: str | None, filename: str | None, content_type: str | None, session_data: dict[str, object]):
        if not contents:
            return no_update, "No correction file uploaded."
        state = load_correction(storage, session_data, UploadPayload(filename=filename, content_type=content_type, content=contents))
        return asdict(state), f"Loaded correction file: {filename or 'unnamed file'}"

    @app.callback(
        Output("session-store", "data", allow_duplicate=True),
        Output("upload-status", "children", allow_duplicate=True),
        Input("upload-session-tg", "contents"),
        State("upload-session-tg", "filename"),
        State("upload-session-tg", "type"),
        prevent_initial_call=True,
    )
    def handle_saved_session_upload(contents: str | None, filename: str | None, content_type: str | None):
        if not contents:
            return no_update, "No saved session uploaded."
        state = import_saved_session(storage, UploadPayload(filename=filename, content_type=content_type, content=contents))
        return asdict(state), f"Imported session archive: {filename or 'session.tg'}"
