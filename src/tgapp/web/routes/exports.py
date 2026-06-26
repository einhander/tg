from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse

from tgapp.application.use_cases import export_session_archive
from tgapp.web.deps import get_or_create_session_state, get_storage

router = APIRouter(prefix="/export")


@router.get("/session")
def export_session(request: Request, response: Response):
    session_state = get_or_create_session_state(request, response)
    archive_path = export_session_archive(get_storage(request), session_state)
    if archive_path is None or not archive_path.exists():
        raise HTTPException(status_code=404, detail="Session archive is unavailable")
    return FileResponse(path=archive_path, filename=archive_path.name, media_type="application/octet-stream")


@router.get("/plot")
def export_plot():
    return PlainTextResponse("Plot export is not implemented yet.", status_code=501)
