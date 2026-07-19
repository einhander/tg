from __future__ import annotations

from dataclasses import asdict

from tgapp.application.dto import SessionStateDto, UiMessage
from tgapp.application.ports import SessionRepository
from tgapp.domain.models import ProcessingSettings
from tgapp.domain.summary import build_effect_text


def calculate_effect(
    storage: SessionRepository,
    session_state: dict[str, object],
    settings: ProcessingSettings,
    xmin: float | None,
    xmax: float | None,
) -> SessionStateDto:
    sid = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(sid, str) or not sid:
        return SessionStateDto(
            session_id=sid,
            status="effect",
            messages=[asdict(UiMessage(text="Тепловой эффект: выделите температурный интервал"))],
        )
    processed = storage.load_frame(storage.processed_path(sid))
    effect_text = build_effect_text(processed, xmin, xmax, settings.init_mass)
    return SessionStateDto(
        session_id=sid,
        status="effect",
        messages=[asdict(UiMessage(text=effect_text))],
    )