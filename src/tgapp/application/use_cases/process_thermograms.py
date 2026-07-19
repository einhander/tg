from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tgapp.application.ports import SessionRepository, ThermogramParser
from tgapp.domain.models import CorrectionFile, ProcessingSettings, ThermogramFile
from tgapp.domain.processing import process_thermograms as _domain_process


def _load_thermogram_models(storage: SessionRepository, session_id: str) -> list[ThermogramFile]:
    return [ThermogramFile(name=name, frame=frame, source_kind="storage") for name, frame in storage.load_thermograms(session_id).items()]


def _load_correction_model(storage: SessionRepository, session_id: str) -> CorrectionFile | None:
    path = storage.correction_path(session_id)
    if not path.exists():
        return None
    return CorrectionFile(name=path.name, frame=storage.load_frame(path))


def process_thermograms(
    storage: SessionRepository,
    session_state: dict[str, object],
    settings: ProcessingSettings,
) -> dict[str, object]:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "no-session"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}

    thermograms = _load_thermogram_models(storage, session_id)
    if not thermograms:
        return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "waiting-for-thermograms"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}

    correction = _load_correction_model(storage, session_id)
    processed = _domain_process(thermograms, settings, correction)
    storage.save_frame(storage.processed_path(session_id), processed.mean_frame)
    storage.save_frame(storage.raw_plot_path(session_id), processed.mean_frame)
    storage.save_json(storage.settings_path(session_id), asdict(settings))
    metadata = storage.load_json(storage.metadata_path(session_id))
    metadata["last_process"] = {
        "heat_speed_text": processed.heat_speed_text,
        "peak_count": len(processed.peaks),
        "adjusted_difflag": processed.adjusted_difflag,
        "summary": asdict(processed.summary),
    }
    metadata["status"] = "processed"
    storage.save_json(storage.metadata_path(session_id), metadata)
    return {
        "settings": asdict(settings),
        "processed_ready": True,
        "summary": asdict(processed.summary),
        "heat_speed_text": processed.heat_speed_text,
        "effect_text": "Тепловой эффект: выделите температурный интервал",
    }