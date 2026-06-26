from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Form, Request, Response

from tgapp.application.use_cases import get_plot_payload, process_session
from tgapp.application.view_models import page_context
from tgapp.domain.models import ProcessingSettings
from tgapp.infrastructure.plotting import build_main_plot, figure_to_json
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates

router = APIRouter()


def _as_bool(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


def _build_settings(current: dict[str, Any], form: dict[str, str | None]) -> ProcessingSettings:
    current_settings = ProcessingSettings(**current) if current else ProcessingSettings()
    base = asdict(current_settings)
    for key, value in form.items():
        if value is None or value == "":
            continue
        if key in {"use_correction", "smooth_dmdt", "hide_tg", "hide_dta", "hide_dtg", "hide_peaks_dta", "hide_peaks_dmdt"}:
            base[key] = _as_bool(value if isinstance(value, str) else None)
        elif key in {"bins", "mass_smoothing", "temp_smoothing", "difflag"}:
            base[key] = int(cast(str, value))
        elif key in {"init_mass", "span"}:
            base[key] = float(cast(str, value))
    return ProcessingSettings(**cast(dict[str, Any], base))


@router.post("/process")
async def process(request: Request, response: Response, init_mass: str | None = Form(None), bins: str | None = Form(None), mass_smoothing: str | None = Form(None), temp_smoothing: str | None = Form(None), difflag: str | None = Form(None), span: str | None = Form(None), use_correction: str | None = Form(None), smooth_dmdt: str | None = Form(None), hide_tg: str | None = Form(None), hide_dta: str | None = Form(None), hide_dtg: str | None = Form(None), hide_peaks_dta: str | None = Form(None), hide_peaks_dmdt: str | None = Form(None)):
    session_state = get_or_create_session_state(request, response)
    existing_processing = get_processing_state(request, session_state)
    form_values: dict[str, str | None] = {
        "init_mass": init_mass,
        "bins": bins,
        "mass_smoothing": mass_smoothing,
        "temp_smoothing": temp_smoothing,
        "difflag": difflag,
        "span": span,
        "use_correction": use_correction,
        "smooth_dmdt": smooth_dmdt,
        "hide_tg": hide_tg,
        "hide_dta": hide_dta,
        "hide_dtg": hide_dtg,
        "hide_peaks_dta": hide_peaks_dta,
        "hide_peaks_dmdt": hide_peaks_dmdt,
    }
    settings = _build_settings(cast(dict[str, Any], existing_processing.get("settings", {})), form_values)
    processing_state = process_session(get_storage(request), session_state, settings)
    plot_payload = get_plot_payload(get_storage(request), session_state, settings)
    figure = build_main_plot(plot_payload)
    plot_json_str = figure_to_json(figure)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        plot_payload=json.loads(plot_json_str),
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/process_response.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)
