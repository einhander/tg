from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tgapp.application.dto import PlotPayload, SessionStateDto, UiMessage
from tgapp.application.ports import SessionRepository
from tgapp.domain.models import ProcessingSettings, ThermogramViewSettings
from tgapp.domain.peaks import detect_peaks


def get_plot_payload(
    storage: SessionRepository,
    session_state: dict[str, object],
    settings: ProcessingSettings,
) -> PlotPayload:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return PlotPayload(settings=asdict(settings), title="Термограмма")

    processed = storage.load_frame(storage.processed_path(session_id))
    peaks = [asdict(peak) for peak in detect_peaks(processed, settings)] if not processed.empty else []
    return PlotPayload(frame_records=processed.to_dict("records"), peaks=peaks, settings=asdict(settings), title="Термограмма")