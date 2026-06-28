from __future__ import annotations

from fastapi import APIRouter, Request, Response

from tgapp.application.use_cases import get_plot_payload
from tgapp.application.view_models import page_context
from tgapp.domain.models import ProcessingSettings
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings

router = APIRouter()


@router.get("/")
def index(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    processing_state = get_processing_state(request, session_state)
    settings = ProcessingSettings(**processing_state.get("settings", {}))
    plot_payload = get_plot_payload(storage, session_state, settings)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        thermogram_settings=get_thermogram_settings(request, session_state),
        plot_payload={
            "title": plot_payload.title,
            "frame_records": plot_payload.frame_records,
            "peaks": plot_payload.peaks,
            "settings": plot_payload.settings,
        },
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="index.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)
