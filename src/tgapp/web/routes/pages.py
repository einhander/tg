from __future__ import annotations

import json

from fastapi import APIRouter, Request, Response

from tgapp.application.use_cases import get_visible_thermogram_plot_json
from tgapp.application.view_models import page_context
from tgapp.domain.models import ThermogramViewSettings
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings

router = APIRouter()


@router.get("/")
def index(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    processing_state = get_processing_state(request, session_state)
    thermogram_settings = get_thermogram_settings(request, session_state)
    plot_json = get_visible_thermogram_plot_json(storage, session_state, ThermogramViewSettings(**thermogram_settings))
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
