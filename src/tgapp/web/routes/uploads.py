from __future__ import annotations

import base64
from dataclasses import asdict

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse
import pandas as pd

from tgapp.application.dto import UploadPayload
from tgapp.application.use_cases import import_saved_session, load_correction, load_thermograms
from tgapp.application.view_models import page_context
from tgapp.domain.models import Tga2PlotSettings
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.web.deps import SESSION_COOKIE_NAME, ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_tga2_settings

router = APIRouter(prefix="/upload")


async def _to_payload(upload: UploadFile) -> UploadPayload:
    raw = await upload.read()
    encoded = base64.b64encode(raw).decode("ascii")
    return UploadPayload(filename=upload.filename, content_type=upload.content_type, content=f"data:{upload.content_type or 'application/octet-stream'};base64,{encoded}")


async def _uploads_from_form(request: Request, *field_names: str) -> list[UploadFile]:
    form = await request.form()
    uploads: list[UploadFile] = []
    for field_name in field_names:
        for item in form.getlist(field_name):
            if hasattr(item, "read") and hasattr(item, "seek") and hasattr(item, "filename"):
                uploads.append(item)
    return uploads


async def _single_upload_from_form(request: Request, *field_names: str) -> UploadFile:
    uploads = await _uploads_from_form(request, *field_names)
    if not uploads:
        raise HTTPException(status_code=422, detail=f"Missing upload field. Expected one of: {', '.join(field_names)}")
    return uploads[0]


@router.post("/thermograms")
async def upload_thermograms(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    thermograms = await _uploads_from_form(request, "thermograms", "thermogramm")
    if not thermograms:
        raise HTTPException(status_code=422, detail="Missing upload field. Expected thermograms or thermogramm.")
    uploads = [await _to_payload(item) for item in thermograms]
    state = load_thermograms(storage, session_state, uploads)
    session_state = asdict(state)
    tga2_settings = get_tga2_settings(request, session_state)
    raw_thermograms = storage.load_raw_thermograms(session_state.get("session_id") or "")
    first_frame = next(iter(raw_thermograms.values()), pd.DataFrame())
    import logging; logging.getLogger("tgapp").info(f"DEBUG: frame columns={list(first_frame.columns)}, shape={first_frame.shape}, hide_tg={tga2_settings.get('hide_tg')}")
    raw_plot_json = figure_to_json(build_raw_plot(first_frame, Tga2PlotSettings(**tga2_settings)))
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=get_processing_state(request, session_state),
        tga2_settings=tga2_settings,
        tga2_plot_json=raw_plot_json,
        upload_status={"message": f"Loaded {len(uploads)} thermogram file(s).", "status": state.status},
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_thermograms_response.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


@router.post("/correction")
async def upload_correction(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    correction = await _single_upload_from_form(request, "correction")
    state = load_correction(get_storage(request), session_state, await _to_payload(correction))
    session_state = asdict(state)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=get_processing_state(request, session_state),
        upload_status={"message": f"Loaded correction file: {correction.filename or 'unnamed file'}", "status": state.status},
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


@router.post("/session")
async def upload_session(request: Request):
    session_file = await _single_upload_from_form(request, "session_file", "data")
    state = import_saved_session(get_storage(request), await _to_payload(session_file))
    storage = get_storage(request)
    metadata = storage.load_json(storage.metadata_path(state.session_id or ""))
    metadata["imported_archive"] = session_file.filename
    metadata["status"] = state.status
    storage.save_json(storage.metadata_path(state.session_id or ""), metadata)
    response = RedirectResponse(url=get_config(request).public_base_path, status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, state.session_id or "", httponly=True, samesite="lax")
    return response
