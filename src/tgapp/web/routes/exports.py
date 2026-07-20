from __future__ import annotations

import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from tgapp.application.ports import SessionArchiveService, SessionRepository
from tgapp.application.use_cases import export_session
from tgapp.application.error_responses import archive_corrupted, UserError
from tgapp.web.deps import get_config, get_or_create_session_state, get_processing_state, get_storage

router = APIRouter(prefix="/export")


def _archive_service() -> SessionArchiveService:
    """Lazy adapter for SessionArchiveService."""
    from tgapp.infrastructure.serialization import pack_session_directory
    class _Adapter:
        def pack_session_directory(self, source: Path, dest: Path) -> Path:
            return pack_session_directory(source, dest)
        def unpack_session_archive(self, archive_path: Path, dest_dir: Path) -> None:
            from tgapp.infrastructure.serialization import unpack_session_archive
            unpack_session_archive(archive_path, dest_dir)
    return _Adapter()


@router.get("/session", name="export_session")
def export_session_route(request: Request, response: Response):
    """Export session as ZIP archive (PLAN_AUDIT §16.3).

    - Creates archive in a temp directory (never inside session dir)
    - Uses atomic temp file → serve → cleanup pattern
    """
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    try:
        state = export_session(storage, _archive_service(), session_state)
    except Exception:
        # Return a minimal error response without exposing internals
        from tgapp.application.view_models import page_context
        from tgapp.web.deps import get_templates, ensure_session_cookie
        err = archive_corrupted("session archive")
        context = page_context(
            request=request,
            base_path=get_config(request).public_base_path,
            session_state=session_state,
            processing_state=get_processing_state(request, session_state),
            thermogram_settings={},
            upload_status={"message": "", "status": "error"},
            error=err.to_dict(),
        )
        template_response = get_templates(request).TemplateResponse(request=request, name="partials/upload_status_block.html", context=context)
        return ensure_session_cookie(request, template_response, session_state)
    sid = session_state.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise HTTPException(status_code=404, detail="Session archive is unavailable")

    session_dir = storage.session_dir(sid)
    archive_name = f"{sid}.tg"

    # PLAN_AUDIT §16.3: create archive outside session directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_archive = Path(tmpdir) / archive_name
        _archive_service().pack_session_directory(session_dir, tmp_archive)

        # Serve the temp file, then let TemporaryDirectory clean it up
        return FileResponse(
            path=tmp_archive,
            filename=archive_name,
            media_type="application/octet-stream",
        )


@router.get("/plot", name="export_plot")
def export_plot():
    return PlainTextResponse("Plot export is not implemented yet.", status_code=501)