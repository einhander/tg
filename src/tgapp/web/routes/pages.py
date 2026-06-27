from __future__ import annotations

import pandas as pd

from fastapi import APIRouter, Request, Response

from tgapp.application.use_cases import get_plot_payload
from tgapp.application.view_models import page_context
from tgapp.domain.models import ProcessingSettings, Tga2PlotSettings
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_tga2_settings

router = APIRouter()


@router.get("/")
def index(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    processing_state = get_processing_state(request, session_state)
    tga2_settings = get_tga2_settings(request, session_state)
    settings = ProcessingSettings(**processing_state.get("settings", {}))
    plot_payload = get_plot_payload(storage, session_state, settings)
    raw_frames = storage.load_thermograms(str(session_state.get("session_id") or ""))
    first_frame = next(iter(raw_frames.values()), pd.DataFrame())
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        tga2_settings=tga2_settings,
        tga2_plot_json=figure_to_json(build_raw_plot(first_frame, Tga2PlotSettings(**tga2_settings))),
        plot_payload={
            "title": plot_payload.title,
            "frame_records": plot_payload.frame_records,
            "peaks": plot_payload.peaks,
            "settings": plot_payload.settings,
        },
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="index.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)
