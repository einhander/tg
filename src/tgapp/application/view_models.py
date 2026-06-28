from __future__ import annotations

from dataclasses import asdict
from typing import Any

from tgapp.application.use_cases import get_heat_speed_text, get_summary
from tgapp.domain.models import ProcessingSettings
from tgapp.infrastructure.serialization import to_json


def _join_base_path(base_path: str, route_path: str) -> str:
    normalized_base = "" if base_path in {"", "/"} else base_path.rstrip("/")
    normalized_route = route_path if route_path.startswith("/") else f"/{route_path}"
    return f"{normalized_base}{normalized_route}" or "/"


def _path_for(request: Any, endpoint: str, **path_params: Any) -> str:
    route_path = str(request.app.url_path_for(endpoint, **path_params))
    base_path = getattr(getattr(request.app.state, "config", None), "base_path", "")
    return _join_base_path(base_path, route_path)


def session_view_model(session_state: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_state.get("session_id"),
        "id": session_state.get("session_id"),
        "session_dir": session_state.get("session_dir"),
        "thermogram_files": list(session_state.get("thermogram_files", []) or []),
        "correction_file": session_state.get("correction_file"),
        "imported_archive": session_state.get("imported_archive"),
        "status": session_state.get("status", "empty"),
        "messages": list(session_state.get("messages", []) or []),
        "has_thermograms": bool(session_state.get("thermogram_files")),
        "has_correction": bool(session_state.get("correction_file")),
    }


def processing_view_model(processing_state: dict[str, Any]) -> dict[str, Any]:
    settings = processing_state.get("settings", {}) if isinstance(processing_state, dict) else {}
    settings_model = ProcessingSettings(**settings) if isinstance(settings, dict) else ProcessingSettings()
    summary = get_summary(processing_state)
    settings_dict = asdict(settings_model)
    return {
        **settings_dict,
        "settings": asdict(settings_model),
        "processed_ready": bool(processing_state.get("processed_ready")) if isinstance(processing_state, dict) else False,
        "summary": processing_state.get("summary", {}) if isinstance(processing_state, dict) else {},
        "summary_lines": summary.lines,
        "summary_metrics": summary.metrics,
        "heat_speed_text": get_heat_speed_text(processing_state),
        "effect_text": str(processing_state.get("effect_text", "Effect: select a temperature interval")) if isinstance(processing_state, dict) else "Effect: select a temperature interval",
    }


def page_context(*, request: Any, base_path: str, session_state: dict[str, Any], processing_state: dict[str, Any], plot_payload: dict[str, Any] | None = None, upload_status: dict[str, Any] | None = None, effect_text: str | None = None, thermogram_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    processing_vm = processing_view_model(processing_state)
    session_vm = session_view_model(session_state)
    session_vm.setdefault("init_mass", processing_vm.get("init_mass", 1.0))
    plot_vm = plot_payload or {}
    plot_json = to_json(plot_vm) if plot_vm else "{}"
    upload_vm = upload_status or {}
    if effect_text is not None:
        processing_vm["effect_text"] = effect_text
    return {
        "request": request,
        "base_path": base_path,
        "upload_thermograms_url": _path_for(request, "upload_thermograms"),
        "upload_session_url": _path_for(request, "upload_session"),
        "upload_correction_url": _path_for(request, "upload_correction"),
        "process_url": _path_for(request, "process"),
        "effect_url": _path_for(request, "effect"),
        "export_plot_url": _path_for(request, "export_plot"),
        "export_session_url": _path_for(request, "export_session"),
        "session": session_vm,
        "session_state": session_vm,
        "processing": processing_vm,
        "processing_state": processing_vm,
        "settings": thermogram_settings or processing_vm.get("settings", {}),
        "plot": plot_vm,
        "plot_payload": plot_vm,
        "plot_payload_json": plot_json,
        "main_plot_json": plot_json,
        "heat_speed_text": processing_vm.get("heat_speed_text", "Heat speed: unavailable"),
        "effect_text": processing_vm.get("effect_text", "Effect: select a temperature interval"),
        "summary_lines": processing_vm.get("summary_lines", []),
        "summary_metrics": processing_vm.get("summary_metrics", {}),
        "upload_status": upload_vm,
        "upload_status_text": str(upload_vm.get("message", "")),
    }
