from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Form, Request, Response

from tgapp.domain.models import ProcessingSettings
from tgapp.application.ports import SessionRepository
from tgapp.application.view_models import page_context
from tgapp.domain.summary import build_effect_text
from tgapp.web.deps import ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates

# Error handling (PLAN_AUDIT §18)
from tgapp.application.error_responses import generic_error, UserError

router = APIRouter()


@router.post("/effect", name="effect")
def effect(request: Request, response: Response, xmin: float | None = Form(None), xmax: float | None = Form(None)):
    session_state = get_or_create_session_state(request, response)
    processing_state = get_processing_state(request, session_state)
    settings_dict = processing_state.get("settings", {})
    settings = ProcessingSettings(**settings_dict) if isinstance(settings_dict, dict) else ProcessingSettings()
    storage = get_storage(request)
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        effect_text = "Тепловой эффект: выделите температурный интервал"
    else:
        try:
            processed = storage.load_frame(storage.processed_path(session_id))
            effect_text = build_effect_text(processed, xmin, xmax, settings.init_mass)
        except Exception:
            effect_text = "Тепловой эффект: ошибка расчёта"
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=processing_state,
        effect_text=effect_text,
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/effect_block.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)