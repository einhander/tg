from __future__ import annotations

from dataclasses import asdict

from tgapp.application.dto import SessionStateDto, UiMessage
from tgapp.application.ports import SessionRepository


def create_session(storage: SessionRepository) -> SessionStateDto:
    session_id = storage.create_session()
    return SessionStateDto(
        session_id=session_id,
        session_dir=str(storage.session_dir(session_id)),
        status="created",
        messages=[asdict(UiMessage(text=f"Session created: {session_id}"))],
    )