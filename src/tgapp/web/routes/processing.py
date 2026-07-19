from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Form, Request, Response

from tgapp.application.use_cases import process_thermograms
from tgapp.application.view_models import page_context
from tgapp.domain.models import ProcessingSettings, ThermogramViewSettings
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings, save_thermogram_settings

router = APIRouter()


def _as_bool(value: str | None) -> bool:
    return str(value).lower() in {"1", "true", "on", "yes"}


HIDE_KEYS = {"hide_tg", "hide_dta", "hide_dtg", "hide_peaks_dta", "hide_peaks_dmdt", "hide_inflections_tg"}
BOOL_KEYS = {"sg_mode"} | HIDE_KEYS


def _build_thermogram_settings(current: dict[str, Any], form: dict[str, str | None]) -> ThermogramViewSettings:
    current_settings = ThermogramViewSettings(**current) if current else ThermogramViewSettings()
    base = asdict(current_settings)
    for key, value in form.items():
        if value is None or value == "":
            continue
        if key in BOOL_KEYS:
            base[key] = _as_bool(value if isinstance(value, str) else None)
        elif key in {"sg_mass_window", "sg_temp_window", "sg_dtg_window"}:
            base[key] = int(cast(str, value))
        elif key in {"peak_prominence_sigma"}:
            base[key] = float(cast(str, value))
    if any(key in form and form[key] is not None for key in HIDE_KEYS):
        for key in HIDE_KEYS:
            if form[key] is None:
                base[key] = False
    return ThermogramViewSettings(**cast(dict[str, Any], base))


def _build_processing_settings(current: dict[str, Any], thermogram_settings: ThermogramViewSettings) -> ProcessingSettings:
    current_settings = ProcessingSettings(**current) if current else ProcessingSettings()
    base = asdict(current_settings)
    base.update(
        {
            "sg_mode": thermogram_settings.sg_mode,
            "sg_window": thermogram_settings.sg_mass_window,
            "peak_prominence_sigma": thermogram_settings.peak_prominence_sigma,
            "hide_tg": thermogram_settings.hide_tg,
            "hide_dta": thermogram_settings.hide_dta,
            "hide_dtg": thermogram_settings.hide_dtg,
            "hide_inflections_tg": thermogram_settings.hide_inflections_tg,
            "hide_peaks_dta": thermogram_settings.hide_peaks_dta,
            "hide_peaks_dmdt": thermogram_settings.hide_peaks_dmdt,
        }
    )
    return ProcessingSettings(**cast(dict[str, Any], base))


def _build_form_values(
    *,
    peak_prominence_sigma: str | None,
    sg_mode: str | None,
    sg_window: str | None,
    sg_mass_window: str | None,
    sg_temp_window: str | None,
    sg_dtg_window: str | None,
    hide_tg: str | None,
    hide_dta: str | None,
    hide_dtg: str | None,
    hide_peaks_dta: str | None,
    hide_peaks_dmdt: str | None,
    hide_inflections_tg: str | None,
    show_tg: str | None,
    show_dta: str | None,
    show_dtg: str | None,
    show_peaks_dta: str | None,
    show_peaks_dmdt: str | None,
    show_inflections_tg: str | None,
) -> dict[str, str | None]:
    resolved_sg_window = sg_window or sg_mass_window or sg_temp_window or sg_dtg_window
    return {
        "peak_prominence_sigma": peak_prominence_sigma,
        "sg_mode": sg_mode,
        "sg_mass_window": sg_mass_window or resolved_sg_window,
        "sg_temp_window": sg_temp_window or resolved_sg_window,
        "sg_dtg_window": sg_dtg_window or resolved_sg_window,
        "hide_tg": hide_tg if hide_tg is not None else (None if show_tg is None else str(int(not _as_bool(show_tg)))),
        "hide_dta": hide_dta if hide_dta is not None else (None if show_dta is None else str(int(not _as_bool(show_dta)))),
        "hide_dtg": hide_dtg if hide_dtg is not None else (None if show_dtg is None else str(int(not _as_bool(show_dtg)))),
        "hide_peaks_dta": hide_peaks_dta if hide_peaks_dta is not None else (None if show_peaks_dta is None else str(int(not _as_bool(show_peaks_dta)))),
        "hide_peaks_dmdt": hide_peaks_dmdt if hide_peaks_dmdt is not None else (None if show_peaks_dmdt is None else str(int(not _as_bool(show_peaks_dmdt)))),
        "hide_inflections_tg": hide_inflections_tg if hide_inflections_tg is not None else (None if show_inflections_tg is None else str(int(not _as_bool(show_inflections_tg)))),
    }


def _render_process_response(request: Request, response: Response, session_state: dict[str, Any], processing_state: dict[str, Any], processing_settings: ProcessingSettings, thermogram_settings: ThermogramViewSettings):
    storage = get_storage(request)
    plot_json_str = _get_visible_thermogram_plot_json(storage, session_state, thermogram_settings)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        thermogram_settings=asdict(thermogram_settings),
        plot_payload=__import__("json").loads(plot_json_str),
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/process_response.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


def _get_visible_thermogram_plot_json(storage, session_state, settings):
    """Infrastructure-dependent plot function — stays in routes."""
    from tgapp.application.dto import PlotPayload
    from tgapp.domain.peaks import detect_peaks
    frame = _load_raw_plot_frame(storage, session_state)
    figure = build_raw_plot(frame, settings)
    return figure_to_json(figure)


def _load_raw_plot_frame(storage, session_state):
    """Infrastructure-dependent data loader — stays in routes."""
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return __import__("pandas").DataFrame()
    raw_thermograms = storage.load_raw_thermograms(session_id)
    if raw_thermograms:
        return next(iter(raw_thermograms.values()))
    thermograms = storage.load_thermograms(session_id)
    if thermograms:
        return next(iter(thermograms.values()))
    return __import__("pandas").DataFrame()


@router.post("/process", name="process")
async def process(request: Request, response: Response, peak_prominence_sigma: str | None = Form(None), sg_mode: str | None = Form(None), sg_window: str | None = Form(None), sg_mass_window: str | None = Form(None), sg_temp_window: str | None = Form(None), sg_dtg_window: str | None = Form(None), hide_tg: str | None = Form(None), hide_dta: str | None = Form(None), hide_dtg: str | None = Form(None), hide_peaks_dta: str | None = Form(None), hide_peaks_dmdt: str | None = Form(None), hide_inflections_tg: str | None = Form(None), show_tg: str | None = Form(None), show_dta: str | None = Form(None), show_dtg: str | None = Form(None), show_peaks_dta: str | None = Form(None), show_peaks_dmdt: str | None = Form(None), show_inflections_tg: str | None = Form(None)):
    session_state = get_or_create_session_state(request, response)
    existing_thermogram_settings = get_thermogram_settings(request, session_state)
    existing_processing = get_processing_state(request, session_state)
    form_values = _build_form_values(
        peak_prominence_sigma=peak_prominence_sigma,
        sg_mode=sg_mode,
        sg_window=sg_window,
        sg_mass_window=sg_mass_window,
        sg_temp_window=sg_temp_window,
        sg_dtg_window=sg_dtg_window,
        hide_tg=hide_tg,
        hide_dta=hide_dta,
        hide_dtg=hide_dtg,
        hide_peaks_dta=hide_peaks_dta,
        hide_peaks_dmdt=hide_peaks_dmdt,
        hide_inflections_tg=hide_inflections_tg,
        show_tg=show_tg,
        show_dta=show_dta,
        show_dtg=show_dtg,
        show_peaks_dta=show_peaks_dta,
        show_peaks_dmdt=show_peaks_dmdt,
        show_inflections_tg=show_inflections_tg,
    )
    thermogram_settings = _build_thermogram_settings(existing_thermogram_settings, form_values)
    save_thermogram_settings(request, session_state, asdict(thermogram_settings))

    processing_settings = _build_processing_settings(cast(dict[str, Any], existing_processing.get("settings", {})), thermogram_settings)
    storage = get_storage(request)
    processing_state = process_thermograms(storage, session_state, processing_settings)
    return _render_process_response(request, response, session_state, processing_state, processing_settings, thermogram_settings)