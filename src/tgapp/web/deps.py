from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import Request, Response

from tgapp.application.session_state import create_default_processing_state, create_default_session_state
from tgapp.application.use_cases import create_session
from tgapp.config import AppConfig
from tgapp.domain.models import ThermogramViewSettings
from tgapp.infrastructure.storage import SessionStorage, validate_session_id

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
    # PLAN_AUDIT §16.1: validate cookie format before touching filesystem
    if session_id and validate_session_id(session_id) and storage.session_dir(session_id).exists():
        return _session_state_from_storage(storage, session_id)

    created = create_session(storage)
    state = asdict(created)
    if response is not None:
        config = get_config(request)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            created.session_id or "",
            httponly=True,
            samesite="lax",
            secure=not config.debug,  # PLAN_AUDIT §16.1: Secure flag in production
        )
    return state


def ensure_session_cookie(request: Request, response: Response, session_state: dict[str, Any]) -> Response:
    session_id = session_state.get("session_id")
    if isinstance(session_id, str) and session_id and request.cookies.get(SESSION_COOKIE_NAME) != session_id:
        config = get_config(request)
        response.set_cookie(
            SESSION_COOKIE_NAME,
            session_id,
            httponly=True,
            samesite="lax",
            secure=not config.debug,  # PLAN_AUDIT §16.1: Secure flag in production
        )
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


def get_thermogram_settings(request: Request, session_state: dict[str, Any]) -> dict[str, Any]:
    """Load unified thermogram settings with backward compatibility."""
    session_id = session_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return asdict(ThermogramViewSettings())

    storage = get_storage(request)

    unified_path = storage.thermogram_settings_path(session_id)
    if unified_path.exists():
        settings = storage.load_json(unified_path)
        if isinstance(settings, dict) and settings:
            return _normalize_thermogram_settings(settings)

    old_settings = storage.load_json(storage.settings_path(session_id))
    old_tga2 = storage.load_json(storage.tga2_settings_path(session_id))

    merged = {}
    if isinstance(old_settings, dict) and old_settings:
        merged.update(old_settings)
    if isinstance(old_tga2, dict) and old_tga2:
        for key in {"sg_mode", "sg_mass_window", "sg_temp_window", "sg_dtg_window", "hide_tg", "hide_dta", "hide_dtg", "hide_peaks_dta", "hide_peaks_dmdt", "hide_inflections_tg", "peak_prominence_sigma"}:
            if key in old_tga2:
                merged[key] = old_tga2[key]

    return _normalize_thermogram_settings(merged)


def _normalize_thermogram_settings(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize raw settings to ThermogramViewSchema."""
    defaults = asdict(ThermogramViewSettings())
    raw_copy = dict(raw)

    legacy_sg_window = raw_copy.get("sg_window")
    if legacy_sg_window is not None:
        for key in ("sg_mass_window", "sg_temp_window", "sg_dtg_window"):
            raw_copy.setdefault(key, legacy_sg_window)

    normalized = {}
    for key, default_val in defaults.items():
        raw_val = raw_copy.get(key)
        if raw_val is None:
            normalized[key] = default_val
        elif isinstance(default_val, bool):
            normalized[key] = bool(raw_val)
        elif isinstance(default_val, int):
            try:
                normalized[key] = int(raw_val)
            except (ValueError, TypeError):
                normalized[key] = default_val
        elif isinstance(default_val, float):
            try:
                normalized[key] = float(raw_val)
            except (ValueError, TypeError):
                normalized[key] = default_val
        else:
            normalized[key] = raw_val
    return normalized


def get_tga2_settings(request: Request, session_state: dict[str, Any]) -> dict[str, Any]:
    """Deprecated: use get_thermogram_settings() instead. Compatibility shim."""
    return get_thermogram_settings(request, session_state)


def save_thermogram_settings(request: Request, session_state: dict[str, Any], settings: dict[str, Any]) -> None:
    """Save unified thermogram settings."""
    session_id = session_state.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        return
    storage = get_storage(request)
    unified_path = storage.thermogram_settings_path(session_id)
    storage.save_json(unified_path, settings)
