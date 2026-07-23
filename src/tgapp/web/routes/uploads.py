from __future__ import annotations

import json
import logging
import os
import tempfile
import base64
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, UploadFile
from fastapi.responses import RedirectResponse

from tgapp.application.dto import UploadPayload
from tgapp.application.ports import DecodedUpload, SessionRepository, ThermogramParser
from tgapp.application.use_cases import import_session, upload_correction, upload_thermograms
from tgapp.application.view_models import page_context
from tgapp.domain.models import (
    InsufficientDataError,
    NonMonotonicAxisError,
    ThermogramValidationError,
    ThermogramViewSettings,
)
from tgapp.infrastructure.file_parsers import (
    decode_upload,
    parse_correction_upload,
    parse_thermogram_uploads,
    parse_thermogram_uploads_streamed,
)
from tgapp.infrastructure.storage import SessionLock, SessionStorage
import pandas as pd

# Error handling (PLAN_AUDIT §18)
from tgapp.application.error_responses import (
    ErrorSeverity,
    archive_corrupted,
    generic_error,
    insufficient_points,
    non_monotonic_temp,
    non_monotonic_time,
    UserError,
)
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.web.deps import SESSION_COOKIE_NAME, ensure_session_cookie, get_config, get_or_create_session_state, get_processing_state, get_storage, get_templates, get_thermogram_settings

router = APIRouter(prefix="/upload")


# PLAN_AUDIT §16.4: upload size limit constant (fallback if config unavailable)
_MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50 MB
_MAX_UPLOAD_FILES = 10


async def _save_uploaded_file(upload: UploadFile) -> tuple[str, str]:
    """Save uploaded file to temporary location with size limit enforcement (PLAN_AUDIT §16.4).

    Returns (temp_path, original_filename).
    Caller is responsible for cleanup.
    """
    # Check Content-Length header first (if present)
    content_length = upload.size
    if content_length is not None and content_length > _MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {content_length} bytes exceeds limit of {_MAX_UPLOAD_SIZE} bytes",
        )

    fd, temp_path = tempfile.mkstemp(suffix=".dat", prefix="tgapp_upload_")
    total_size = 0

    try:
        while True:
            chunk = await upload.read(8192)  # 8KB chunks
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > _MAX_UPLOAD_SIZE:
                os.close(fd)
                os.unlink(temp_path)
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large: {total_size} bytes exceeds limit of {_MAX_UPLOAD_SIZE} bytes",
                )
            os.write(fd, chunk)
    finally:
        os.close(fd)

    return temp_path, upload.filename or "upload"


async def _to_payload(upload: UploadFile) -> UploadPayload:
    """Read upload content with size limit enforcement (PLAN_AUDIT §16.4).
    
    Legacy Base64 path — kept for correction/session upload routes.
    """
    content_length = upload.size
    if content_length is not None and content_length > _MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {content_length} bytes exceeds limit of {_MAX_UPLOAD_SIZE} bytes",
        )
    raw = await upload.read()
    if len(raw) > _MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {len(raw)} bytes exceeds limit of {_MAX_UPLOAD_SIZE} bytes",
        )
    encoded = base64.b64encode(raw).decode("ascii")
    return UploadPayload(filename=upload.filename, content_type=upload.content_type, content=f"data:{upload.content_type or 'application/octet-stream'};base64,{encoded}")


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
            validated = storage.load_validated_thermograms(session_id)
            if validated:
                frame = next(iter(validated.values()))
            else:
                return figure_to_json(build_raw_plot(__import__("pandas").DataFrame(), settings))
    return figure_to_json(build_raw_plot(frame, settings))


logger = logging.getLogger(__name__)


@router.post("/thermograms", name="upload_thermograms")
async def upload_thermograms_route(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    session_id = session_state.get("session_id", "")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=500, detail="Invalid session")

    # PLAN_AUDIT §17.2: exclusive lock on session during write operations
    lock = SessionLock(storage, session_id)
    try:
        lock.acquire()
    except RuntimeError:
        err = UserError(
            message="Сессия заблокирована. Повторите попытку через несколько секунд.",
            severity=ErrorSeverity.WARNING,
        )
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_thermograms_response.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)

    try:
        return await _upload_thermograms_inner(request, response, storage, session_state)
    finally:
        lock.release()


async def _upload_thermograms_inner(
    request: Request, response: Response, storage: SessionStorage, session_state: dict[str, Any],
) -> Response:
    """Inner upload logic (protected by SessionLock)."""
    thermograms = await _uploads_from_form(request, "thermograms", "thermogramm")
    if not thermograms:
        raise HTTPException(status_code=422, detail="Missing upload field. Expected thermograms or thermogramm.")
    # PLAN_AUDIT §16.4: file count limit
    if len(thermograms) > _MAX_UPLOAD_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files: {len(thermograms)} exceeds limit of {_MAX_UPLOAD_FILES}",
        )

    # Streaming: save to temp files, parse from disk, clean up
    temp_files: list[tuple[str, str]] = []  # (temp_path, filename)
    try:
        # 1. Save uploads to temp files with size enforcement
        for item in thermograms:
            temp_path, filename = await _save_uploaded_file(item)
            temp_files.append((temp_path, filename))

        # 2. Parse from temp files (streaming — no Base64, no full-RAM copy)
        parsed_files = parse_thermogram_uploads_streamed(temp_files)

        # 3. Inline validation logic (same as upload_thermograms use case)
        from tgapp.domain.models import UploadedThermogramResult, ValidatedThermogram
        from tgapp.domain.validator import validate_parsed
        from tgapp.application._helpers import validated_to_df

        file_results: list[UploadedThermogramResult] = []
        validated_frames: dict[str, pd.DataFrame] = {}

        for index, parsed_file in enumerate(parsed_files):
            parsed = _PARSER.frame_to_parsed(
                parsed_file.name,
                parsed_file.frame,
                parsed_file.metadata.get("content_type", ""),
            )
            parsed_rows = len(parsed.temp) if parsed.temp is not None else 0

            if parsed_rows == 0:
                file_results.append(UploadedThermogramResult(
                    original_name=parsed_file.name,
                    accepted=False,
                    stored_name=None,
                    parsed_rows=0,
                    validated_rows=0,
                    rows_removed=0,
                    rows_interpolated=0,
                    errors=("Файл не содержит данных после парсинга.",),
                ))
                continue

            try:
                validated = validate_parsed(parsed.temp, parsed.deltatemp, parsed.time, parsed.mass)
                validated = ValidatedThermogram(
                    name=parsed_file.name,
                    temp=validated.temp,
                    deltatemp=validated.deltatemp,
                    time=validated.time,
                    mass=validated.mass,
                    metadata=validated.metadata,
                )
                validated_df = validated_to_df(validated)
                validated_key = f"validated_thermogram_{index + 1}.csv"
                validated_frames[validated_key] = validated_df
                file_results.append(UploadedThermogramResult(
                    original_name=parsed_file.name,
                    accepted=True,
                    stored_name=validated_key,
                    parsed_rows=parsed_rows,
                    validated_rows=len(validated.temp),
                    rows_removed=validated.metadata.get("rows_removed", 0),
                    rows_interpolated=validated.metadata.get("rows_interpolated", 0),
                    warnings=(),
                    errors=(),
                ))
            except (NonMonotonicAxisError, InsufficientDataError, ThermogramValidationError):
                raise  # Bubble up to route-level handler
            except Exception as e:
                logger.warning("Validation failed for %s: %s", parsed_file.name, e)
                file_results.append(UploadedThermogramResult(
                    original_name=parsed_file.name,
                    accepted=False,
                    stored_name=None,
                    parsed_rows=parsed_rows,
                    validated_rows=0,
                    rows_removed=0,
                    rows_interpolated=0,
                    errors=(str(e),),
                ))

        # 4. Save validated thermograms
        session_id = session_state.get("session_id", "")
        storage.save_validated_thermograms(session_id, validated_frames)

        # 5. Calculate summary stats
        accepted_count = sum(1 for r in file_results if r.accepted)
        rejected_count = sum(1 for r in file_results if not r.accepted)

        # 6. Determine status
        if accepted_count == 0:
            status = "thermograms-not-accepted"
        elif rejected_count > 0:
            status = "thermograms-partially-loaded"
        else:
            status = "thermograms-loaded"

        # 7. Build metadata
        metadata = {
            "original_names": [item.name for item in parsed_files],
            "status": status,
            "file_results": [asdict(r) for r in file_results],
            "accepted_count": accepted_count,
            "rejected_count": rejected_count,
        }
        storage.save_json(storage.metadata_path(session_id), metadata)

        # 8. Build user message
        if accepted_count == 0:
            msg = f"Загружено файлов: {len(parsed_files)}. Принято к обработке: 0. Отклонено: {rejected_count}."
            for r in file_results:
                if not r.accepted and r.errors:
                    msg += f"\n{r.original_name}: {r.errors[0]}"
        elif rejected_count > 0:
            msg = f"Загружено файлов: {len(parsed_files)}. Принято к обработке: {accepted_count}. Отклонено: {rejected_count}."
            for r in file_results:
                if not r.accepted and r.errors:
                    msg += f"\n{r.original_name}: {r.errors[0]}"
        else:
            msg = f"Загружено файлов: {len(parsed_files)}. Принято к обработке: {accepted_count}."

        # 9. Success response
        session_state["session_id"] = session_id
        session_state["status"] = status
        session_state["thermogram_files"] = list(validated_frames.keys()) if validated_frames else []

        thermogram_settings = get_thermogram_settings(request, session_state)
        plot_json = _get_visible_thermogram_plot_json(
            storage, session_state, ThermogramViewSettings(**thermogram_settings)
        )
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=thermogram_settings,
            plot_payload=json.loads(plot_json),
            upload_status={"message": msg, "status": status},
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_thermograms_response.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)

    except InsufficientDataError as e:
        err = insufficient_points(e.details.get("n", 0) if isinstance(e.details, dict) else 0)
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_thermograms_response.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)
    except NonMonotonicAxisError as e:
        msg_lower = str(e).lower()
        if "время" in msg_lower or "time" in msg_lower:
            err = non_monotonic_time()
        else:
            err = non_monotonic_temp()
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_thermograms_response.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)
    except ThermogramValidationError as e:
        err = UserError(message=str(e), severity=ErrorSeverity.ERROR)
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_thermograms_response.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)
    except Exception as e:
        err = generic_error()
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_thermograms_response.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)
    finally:
        # Always clean up temp files
        for temp_path, _ in temp_files:
            try:
                os.unlink(temp_path)
            except OSError:
                pass


@router.post("/correction", name="upload_correction")
async def upload_correction_route(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    session_id = session_state.get("session_id", "")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=500, detail="Invalid session")

    lock = SessionLock(storage, session_id)
    try:
        lock.acquire()
    except RuntimeError:
        err = UserError(
            message="Сессия заблокирована. Повторите попытку через несколько секунд.",
            severity=ErrorSeverity.WARNING,
        )
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_status_block.html", context=context
        )
        return ensure_session_cookie(request, template_response, session_state)

    try:
        state = upload_correction(storage, _PARSER, session_state, await _to_payload(await _single_upload_from_form(request, "correction")))
    except ThermogramValidationError as e:
        err = UserError(message=str(e), severity=ErrorSeverity.ERROR)
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
        return ensure_session_cookie(request, template_response, session_state)
    except Exception as e:
        err = generic_error()
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings=get_thermogram_settings(request, session_state),
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
        return ensure_session_cookie(request, template_response, session_state)
    finally:
        lock.release()

    session_state = asdict(state)
    context = page_context(
        request=request,
        base_path=get_config(request).public_base_path,
        session_state=session_state,
        processing_state=get_processing_state(request, session_state),
        thermogram_settings=get_thermogram_settings(request, session_state),
        upload_status={"message": f"Loaded correction file: {session_state.get('correction_file', 'unnamed file')}", "status": state.status},
    )
    template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
    return ensure_session_cookie(request, template_response, session_state)


@router.post("/session", name="upload_session")
async def upload_session(request: Request):
    session_file = await _single_upload_from_form(request, "session_file", "data")
    session_state = get_or_create_session_state(request, Response())
    storage = get_storage(request)
    session_id = session_state.get("session_id", "")
    if not isinstance(session_id, str) or not session_id:
        raise HTTPException(status_code=500, detail="Invalid session")

    lock = SessionLock(storage, session_id)
    try:
        lock.acquire()
    except RuntimeError:
        err = UserError(
            message="Сессия заблокирована. Повторите попытку через несколько секунд.",
            severity=ErrorSeverity.WARNING,
        )
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state={},
            thermogram_settings={},
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(
            request=request, name="partials/upload_status_block.html", context=context
        )
        response = Response()
        return ensure_session_cookie(request, template_response, session_state)

    try:
        state = import_session(storage, _ARCHIVE, _PARSER, await _to_payload(session_file))
    except Exception as e:
        err = archive_corrupted(session_file.filename or "archive")
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state={},
            thermogram_settings={},
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
        response = Response()
        return ensure_session_cookie(request, template_response, session_state)
    finally:
        lock.release()

    metadata = storage.load_json(storage.metadata_path(state.session_id or ""))
    metadata["imported_archive"] = session_file.filename
    metadata["status"] = state.status
    storage.save_json(storage.metadata_path(state.session_id or ""), metadata)
    response = RedirectResponse(url=get_config(request).public_base_path, status_code=303)
    config = get_config(request)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        state.session_id or "",
        httponly=True,
        samesite="lax",
        secure=not config.debug,  # PLAN_AUDIT §16.1
    )
    return response