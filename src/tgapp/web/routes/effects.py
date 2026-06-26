from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response

from tgapp.application.use_cases import get_effect_text
from tgapp.domain.models import ProcessingSettings
from tgapp.application.view_models import page_context
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates

router = APIRouter()


@router.post("/effect")
def effect(request: Request, response: Response, xmin: float | None = Form(None), xmax: float | None = Form(None)):
    session_state = get_or_create_session_state(request, response)
    processing_state = get_processing_state(request, session_state)
    settings = ProcessingSettings(**processing_state.get("settings", {}))
    effect_text = get_effect_text(get_storage(request), session_state, settings, xmin, xmax)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        effect_text=effect_text,
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/effect_block.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)
