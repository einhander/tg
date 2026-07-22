from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import Any, cast

from fastapi import APIRouter, Form, HTTPException, Request, Response

from tgapp.application.use_cases import process_thermograms
from tgapp.application.view_models import page_context
from tgapp.domain.models import ProcessingSettings, ThermogramViewSettings
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.infrastructure.storage import SessionLock
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings, save_thermogram_settings

# Error handling (PLAN_AUDIT §18)
from tgapp.application.error_responses import (
    ErrorSeverity,
    correction_coverage_error,
    generic_error,
    no_common_range,
    recovery_warning,
    UserError,
)
from tgapp.domain.models import (
    CorrectionRangeError,
    NoCommonRangeError,
    ThermogramValidationError,
)

router = APIRouter()

logger = logging.getLogger(__name__)


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


def _render_process_response(request: Request, response: Response, session_state: dict[str, Any], processing_state: dict[str, Any], processing_settings: ProcessingSettings, thermogram_settings: ThermogramViewSettings, error: dict[str, Any] | None = None, recovery_warning: dict[str, Any] | None = None):
    storage = get_storage(request)
    plot_json_str = _get_visible_thermogram_plot_json(storage, session_state, thermogram_settings)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        thermogram_settings=asdict(thermogram_settings),
        plot_payload=__import__("json").loads(plot_json_str),
        error=error,
        recovery_warning=recovery_warning,
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
    storage = get_storage(request)
    session_id = session_state.get("session_id", "")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=500, detail="Invalid session")

    # PLAN_AUDIT §17.2: exclusive lock on session during processing
    lock = SessionLock(storage, session_id)
    try:
        lock.acquire()
    except RuntimeError:
        processing_state = {
            "settings": {},
            "processed_ready": False,
            "summary": {"status": "locked"},
            "heat_speed_text": "Скорость нагрева: недоступна",
            "effect_text": "Тепловой эффект: недоступен",
            "error": UserError(
                message="Сессия заблокирована. Повторите попытку через несколько секунд.",
                severity=ErrorSeverity.WARNING,
            ).to_dict(),
        }
        return _render_process_response(
            request, response, session_state, processing_state,
            ProcessingSettings(), ThermogramViewSettings(),
            error=processing_state.get("error"),
        )

    try:
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

        # PLAN_AUDIT §17.5: offload CPU-bound processing to thread pool
        try:
            processing_state = await asyncio.to_thread(
                process_thermograms, storage, session_state, processing_settings
            )
        except NoCommonRangeError:
            processing_state = {
                "settings": asdict(processing_settings),
                "processed_ready": False,
                "summary": {"status": "no-common-range"},
                "heat_speed_text": "Скорость нагрева: недоступна",
                "effect_text": "Тепловой эффект: выделите температурный интервал",
                "error": no_common_range().to_dict(),
            }
        except CorrectionRangeError as e:
            details = getattr(e, "details", {})
            if isinstance(details, dict):
                err = correction_coverage_error(
                    details.get("min_temp", 0), details.get("max_temp", 0),
                    details.get("corr_min", 0), details.get("corr_max", 0),
                )
            else:
                err = generic_error(str(e))
            processing_state = {
                "settings": asdict(processing_settings),
                "processed_ready": False,
                "summary": {"status": "correction-range-error"},
                "heat_speed_text": "Скорость нагрева: недоступна",
                "effect_text": "Тепловой эффект: выделите температурный интервал",
                "error": err.to_dict(),
            }
        except ThermogramValidationError as e:
            processing_state = {
                "settings": asdict(processing_settings),
                "processed_ready": False,
                "summary": {"status": "validation-error"},
                "heat_speed_text": "Скорость нагрева: недоступна",
                "effect_text": "Тепловой эффект: выделите температурный интервал",
                "error": UserError(message=str(e), severity=ErrorSeverity.ERROR).to_dict(),
            }
        except Exception as e:
            processing_state = {
                "settings": asdict(processing_settings),
                "processed_ready": False,
                "summary": {"status": "error"},
                "heat_speed_text": "Скорость нагрева: недоступна",
                "effect_text": "Тепловой эффект: выделите температурный интервал",
                "error": generic_error().to_dict(),
            }

        # PLAN_AUDIT §17.3: check session size after processing
        config = get_config(request)
        try:
            storage.check_session_size(session_id, config.max_session_size)
        except ValueError as e:
            logger.warning("Session size exceeded after processing: %s", e)
            # Data already saved — mark as ready but log warning
            processing_state.setdefault("summary", {})["status"] = "session-size-exceeded"
            processing_state["recovery_warning"] = UserError(
                message=f"Размер сессии превышает лимит ({config.max_session_size} байт). Рассмотрите очистку старых сессий.",
                severity=ErrorSeverity.WARNING,
            ).to_dict()

        # Add recovery warning if present in processing_state
        error_dict = processing_state.get("error") if isinstance(processing_state, dict) else None
        recovery_dict = processing_state.get("recovery_warning") if isinstance(processing_state, dict) else None
        return _render_process_response(
            request, response, session_state, processing_state,
            processing_settings, thermogram_settings,
            error=error_dict, recovery_warning=recovery_dict,
        )
    finally:
        lock.release()