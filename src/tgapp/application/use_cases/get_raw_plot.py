from __future__ import annotations

from pathlib import Path

from tgapp.application.dto import SessionStateDto
from tgapp.application.ports import SessionRepository


def get_raw_plot(
    storage: SessionRepository,
    session_state: dict[str, object],
) -> Path | None:
    """Return path to raw plot CSV, or None."""
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return None
    raw_path = storage.raw_plot_path(session_id)
    if raw_path.exists():
        return raw_path
    return None