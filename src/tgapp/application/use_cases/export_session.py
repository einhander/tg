from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tgapp.application.dto import SessionStateDto, UiMessage
from tgapp.application.ports import SessionArchiveService, SessionRepository


def export_session(
    storage: SessionRepository,
    archive_service: SessionArchiveService,
    session_state: dict[str, object],
) -> SessionStateDto:
    sid = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(sid, str) or not sid:
        return SessionStateDto(
            session_id=sid,
            status="error",
            messages=[asdict(UiMessage(text="No active session"))],
        )
    return SessionStateDto(
        session_id=sid,
        session_dir=str(storage.session_dir(sid)),
        status="exported",
        messages=[asdict(UiMessage(text=f"Session exported: {sid}.tg"))],
    )