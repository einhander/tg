from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from tgapp.application.view_models import page_context
from tgapp.domain.models import ThermogramViewSettings
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings

router = APIRouter()


def _get_visible_thermogram_plot_json(storage, session_state, settings):
    """Infrastructure-dependent plot function — stays in routes."""
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return figure_to_json(build_raw_plot(__import__("pandas").DataFrame(), settings))
    raw_thermograms = storage.load_raw_thermograms(session_id)
    if raw_thermograms:
        frame = next(iter(raw_thermograms.values()))
    else:
        thermograms = storage.load_thermograms(session_id)
        if thermograms:
            frame = next(iter(thermograms.values()))
        else:
            return figure_to_json(build_raw_plot(__import__("pandas").DataFrame(), settings))
    return figure_to_json(build_raw_plot(frame, settings))


@router.get("/")
def index(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    processing_state = get_processing_state(request, session_state)
    thermogram_settings = get_thermogram_settings(request, session_state)
    plot_json = _get_visible_thermogram_plot_json(storage, session_state, ThermogramViewSettings(**thermogram_settings))
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        thermogram_settings=thermogram_settings,
        plot_payload=json.loads(plot_json),
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="index.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)