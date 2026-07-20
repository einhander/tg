from __future__ import annotations

import base64
from dataclasses import asdict
import json

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse

from tgapp.application.dto import UploadPayload
from tgapp.application.ports import DecodedUpload, SessionRepository, ThermogramParser
from tgapp.application.use_cases import import_session, upload_correction, upload_thermograms
from tgapp.application.view_models import page_context
from tgapp.domain.models import ThermogramViewSettings
from tgapp.infrastructure.file_parsers import decode_upload, parse_correction_upload, parse_thermogram_uploads
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.web.deps import SESSION_COOKIE_NAME, ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings

router = APIRouter(prefix="/upload")


# Adapter: wrap module-level functions as ThermogramParser Protocol implementation
class _FileParserAdapter(ThermogramParser):
    def parse_thermogram_uploads(self, uploads: list[UploadPayload]) -> list:
        return parse_thermogram_uploads(uploads)

    def parse_correction_upload(self, upload: UploadPayload):
        return parse_correction_upload(upload)

    def decode_upload(self, upload: UploadPayload) -> DecodedUpload:
        return decode_upload(upload)

    def frame_to_parsed(self, name: str, frame, content_type: str = ""):
        from tgapp.infrastructure.file_parsers import frame_to_parsed as _frame_to_parsed
        return _frame_to_parsed(name, frame, content_type)


# Adapter: wrap module-level functions as SessionArchiveService Protocol implementation
class _ArchiveServiceAdapter:
    def pack_session_directory(self, source, dest):
        from tgapp.infrastructure.serialization import pack_session_directory
        return pack_session_directory(source, dest)

    def unpack_session_archive(self, archive_path, dest_dir):
        from tgapp.infrastructure.serialization import unpack_session_archive
        unpack_session_archive(archive_path, dest_dir)


_PARSER = _FileParserAdapter()
_ARCHIVE = _ArchiveServiceAdapter()


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


def _get_visible_thermogram_plot_json(storage, session_state, settings):
    """Infrastructure-dependent plot function — stays in routes."""
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        from tgapp.domain.models import ThermogramViewSettings
        return figure_to_json(build_raw_plot(__import__("pandas").DataFrame(), settings or ThermogramViewSettings()))
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


@router.post("/thermograms", name="upload_thermograms")
async def upload_thermograms_route(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    thermograms = await _uploads_from_form(request, "thermograms", "thermogramm")
    if not thermograms:
        raise HTTPException(status_code=422, detail="Missing upload field. Expected thermograms or thermogramm.")
    uploads = [await _to_payload(item) for item in thermograms]
    state = upload_thermograms(storage, _PARSER, session_state, uploads)
    session_state = asdict(state)
    thermogram_settings = get_thermogram_settings(request, session_state)
    plot_json = _get_visible_thermogram_plot_json(storage, session_state, ThermogramViewSettings(**thermogram_settings))
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=get_processing_state(request, session_state),
        thermogram_settings=thermogram_settings,
        plot_payload=json.loads(plot_json),
        upload_status={"message": f"Loaded {len(uploads)} thermogram file(s).", "status": state.status},
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_thermograms_response.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


@router.post("/correction", name="upload_correction")
async def upload_correction_route(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    correction = await _single_upload_from_form(request, "correction")
    state = upload_correction(get_storage(request), _PARSER, session_state, await _to_payload(correction))
    session_state = asdict(state)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=get_processing_state(request, session_state),
        thermogram_settings=get_thermogram_settings(request, session_state),
        upload_status={"message": f"Loaded correction file: {correction.filename or 'unnamed file'}", "status": state.status},
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


@router.post("/session", name="upload_session")
async def upload_session(request: Request):
    session_file = await _single_upload_from_form(request, "session_file", "data")
    state = import_session(get_storage(request), _ARCHIVE, _PARSER, await _to_payload(session_file))
    storage = get_storage(request)
    metadata = storage.load_json(storage.metadata_path(state.session_id or ""))
    metadata["imported_archive"] = session_file.filename
    metadata["status"] = state.status
    storage.save_json(storage.metadata_path(state.session_id or ""), metadata)
    response = RedirectResponse(url=get_config(request).public_base_path, status_code=303)
    response.set_cookie(SESSION_COOKIE_NAME, state.session_id or "", httponly=True, samesite="lax")
    return response