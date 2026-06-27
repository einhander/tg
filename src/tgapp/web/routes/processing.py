from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, cast

import pandas as pd
from fastapi import APIRouter, Form, Request, Response

from tgapp.application.use_cases import get_plot_payload, process_session
from tgapp.application.view_models import page_context
from tgapp.domain.models import ProcessingSettings, Tga2PlotSettings
from tgapp.infrastructure.plotting import build_main_plot, build_raw_plot, figure_to_json
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_tga2_settings

router = APIRouter()


def _as_bool(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


HIDE_KEYS = {"hide_tg", "hide_dta", "hide_dtg", "hide_peaks_dta", "hide_peaks_dmdt"}
BOOL_KEYS = {"use_correction", "smooth_dmdt", "sg_mode"} | HIDE_KEYS


def _build_settings(current: dict[str, Any], form: dict[str, str | None]) -> ProcessingSettings:
    current_settings = ProcessingSettings(**current) if current else ProcessingSettings()
    base = asdict(current_settings)
    for key, value in form.items():
        if value is None or value == "":
            continue
        if key in BOOL_KEYS:
            base[key] = _as_bool(value if isinstance(value, str) else None)
        elif key in {"bins", "mass_smoothing", "temp_smoothing", "difflag", "sg_window", "sg_polyorder"}:
            base[key] = int(cast(str, value))
        elif key in {"init_mass", "span"}:
            base[key] = float(cast(str, value))
    # Unchecked checkboxes send nothing; reset missing hide keys to False
    # when any hide key is present (means visibility form was submitted)
    if any(key in form and form[key] is not None for key in HIDE_KEYS):
        for key in HIDE_KEYS:
            if form[key] is None:
                base[key] = False
    return ProcessingSettings(**cast(dict[str, Any], base))


TGA2_HIDE_KEYS = {"hide_tg", "hide_dta", "hide_dtg"}
# TGA2 UI submits positive show_* flags; persisted/settings model stays hide_*.
TGA2_SHOW_TO_HIDE = {
    "show_tg": "hide_tg",
    "show_dta": "hide_dta",
    "show_dtg": "hide_dtg",
}
TGA2_BOOL_KEYS = {"sg_mode"}


def _build_tga2_settings(current: dict[str, Any], form: dict[str, str | None]) -> Tga2PlotSettings:
    # Filter current settings to only include valid Tga2PlotSettings fields
    valid_fields = {"sg_mode", "sg_mass_window", "sg_temp_window", "sg_dtg_window", "hide_tg", "hide_dta", "hide_dtg"}
    filtered_current = {k: v for k, v in current.items() if k in valid_fields} if current else {}
    # Backward compat: map old sg_window to both new windows
    if "sg_window" in current and "sg_mass_window" not in filtered_current:
        filtered_current["sg_mass_window"] = current["sg_window"]
        filtered_current["sg_temp_window"] = current["sg_window"]
    current_settings = Tga2PlotSettings(**filtered_current) if filtered_current else Tga2PlotSettings()
    base = asdict(current_settings)
    for key, value in form.items():
        if value is None or value == "":
            continue
        if key in TGA2_BOOL_KEYS:
            base[key] = _as_bool(value if isinstance(value, str) else None)
        elif key in TGA2_SHOW_TO_HIDE:
            base[TGA2_SHOW_TO_HIDE[key]] = not _as_bool(value if isinstance(value, str) else None)
        elif key in {"sg_mass_window", "sg_temp_window", "sg_dtg_window"}:
            base[key] = int(cast(str, value))
        # Backward compat: old sg_window maps to both new windows
        elif key == "sg_window":
            base["sg_mass_window"] = int(cast(str, value))
            base["sg_temp_window"] = int(cast(str, value))
    return Tga2PlotSettings(**cast(dict[str, Any], base))


@router.post("/process")
async def process(request: Request, response: Response, init_mass: str | None = Form(None), bins: str | None = Form(None), mass_smoothing: str | None = Form(None), temp_smoothing: str | None = Form(None), difflag: str | None = Form(None), span: str | None = Form(None), use_correction: str | None = Form(None), smooth_dmdt: str | None = Form(None), sg_mode: str | None = Form(None), sg_window: str | None = Form(None), sg_polyorder: str | None = Form(None), hide_tg: str | None = Form(None), hide_dta: str | None = Form(None), hide_dtg: str | None = Form(None), hide_peaks_dta: str | None = Form(None), hide_peaks_dmdt: str | None = Form(None)):
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
        "sg_mode": sg_mode,
        "sg_window": sg_window,
        "sg_polyorder": sg_polyorder,
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
        tga2_settings=get_tga2_settings(request, session_state),
        plot_payload=json.loads(plot_json_str),
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/process_response.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


@router.post("/tga2/plot", name="update_tga2_plot")
async def update_tga2_plot(request: Request, response: Response, sg_mode: str | None = Form(None), sg_mass_window: str | None = Form(None), sg_temp_window: str | None = Form(None), sg_dtg_window: str | None = Form(None), show_tg: str | None = Form(None), show_dta: str | None = Form(None), show_dtg: str | None = Form(None)):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    session_id = session_state.get("session_id")
    settings = _build_tga2_settings(
        get_tga2_settings(request, session_state),
        {
            "sg_mode": sg_mode,
            "sg_mass_window": sg_mass_window,
            "sg_temp_window": sg_temp_window,
            "sg_dtg_window": sg_dtg_window,
            "show_tg": show_tg,
            "show_dta": show_dta,
            "show_dtg": show_dtg,
        },
    )
    if isinstance(session_id, str) and session_id:
        storage.save_json(storage.tga2_settings_path(session_id), asdict(settings))

    raw_frames = storage.load_raw_thermograms(session_id) if isinstance(session_id, str) and session_id else {}
    first_frame = next(iter(raw_frames.values()), pd.DataFrame())
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=get_processing_state(request, session_state),
        tga2_settings=asdict(settings),
        tga2_plot_json=figure_to_json(build_raw_plot(first_frame, settings)),
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/tga2_plot_response.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)
