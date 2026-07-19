from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from tgapp.application.ports import SessionArchiveService, SessionRepository
from tgapp.application.use_cases import export_session
from tgapp.web.deps import get_or_create_session_state, get_storage

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
    session_state = get_or_create_session_state(request, response)
    storage = get_storage(request)
    state = export_session(storage, _archive_service(), session_state)
    sid = session_state.get("session_id")
    if not isinstance(sid, str) or not sid:
        raise HTTPException(status_code=404, detail="Session archive is unavailable")
    archive_path = storage.session_dir(sid) / f"{sid}.tg"
    if not archive_path.exists():
        raise HTTPException(status_code=404, detail="Session archive is unavailable")
    return FileResponse(path=archive_path, filename=archive_path.name, media_type="application/octet-stream")


@router.get("/plot", name="export_plot")
def export_plot():
    return PlainTextResponse("Plot export is not implemented yet.", status_code=501)