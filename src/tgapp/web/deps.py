from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import Request, Response

from tgapp.application.session_state import create_default_processing_state, create_default_session_state
from tgapp.application.use_cases import create_session
from tgapp.config import AppConfig
from tgapp.domain.models import Tga2PlotSettings
from tgapp.infrastructure.storage import SessionStorage

SESSION_COOKIE_NAME = "tgapp_session_id"


def get_config(request: Request) -> AppConfig:
    return request.app.state.config


def get_storage(request: Request) -> SessionStorage:
    return request.app.state.storage


def get_templates(request: Request):
    return request.app.state.templates


def _session_state_from_storage(storage: SessionStorage, session_id: str) -> dict[str, Any]:
    state = create_default_session_state()
    state["session_id"] = session_id
    state["session_dir"] = str(storage.session_dir(session_id))
    state["thermogram_files"] = list(storage.load_thermograms(session_id).keys())
    correction_path = storage.correction_path(session_id)
    state["correction_file"] = correction_path.name if correction_path.exists() else None
    metadata = storage.load_json(storage.metadata_path(session_id))
    state["imported_archive"] = metadata.get("imported_archive")
    state["status"] = metadata.get("status", "ready")
    return state


def get_or_create_session_state(request: Request, response: Response | None = None) -> dict[str, Any]:
    storage = get_storage(request)
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id and storage.session_dir(session_id).exists():
        return _session_state_from_storage(storage, session_id)

    created = create_session(storage)
    state = asdict(created)
    if response is not None:
        response.set_cookie(SESSION_COOKIE_NAME, created.session_id or "", httponly=True, samesite="lax")
    return state


def ensure_session_cookie(request: Request, response: Response, session_state: dict[str, Any]) -> Response:
    session_id = session_state.get("session_id")
    if isinstance(session_id, str) and session_id and request.cookies.get(SESSION_COOKIE_NAME) != session_id:
        response.set_cookie(SESSION_COOKIE_NAME, session_id, httponly=True, samesite="lax")
    return response


def get_processing_state(request: Request, session_state: dict[str, Any]) -> dict[str, Any]:
    processing_state = create_default_processing_state()
    session_id = session_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return processing_state

    settings = get_storage(request).load_json(get_storage(request).settings_path(session_id))
    metadata = get_storage(request).load_json(get_storage(request).metadata_path(session_id))
    last_process = metadata.get("last_process", {}) if isinstance(metadata, dict) else {}
    if isinstance(settings, dict) and settings:
        processing_state["settings"] = settings
    processed_exists = get_storage(request).processed_path(session_id).exists()
    processing_state["processed_ready"] = processed_exists
    processing_state["summary"] = last_process.get("summary", processing_state.get("summary", {}))
    processing_state["heat_speed_text"] = last_process.get("heat_speed_text", processing_state.get("heat_speed_text"))
    processing_state["effect_text"] = "Effect: select a temperature interval"
    return processing_state


def get_tga2_settings(request: Request, session_state: dict[str, Any]) -> dict[str, Any]:
    session_id = session_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return asdict(Tga2PlotSettings())

    settings = get_storage(request).load_json(get_storage(request).tga2_settings_path(session_id))
    if isinstance(settings, dict) and settings:
        return asdict(Tga2PlotSettings(**settings))
    return asdict(Tga2PlotSettings())
