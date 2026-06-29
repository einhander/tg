from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import pandas as pd

from tgapp.application.dto import PlotPayload, SessionStateDto, UiMessage, UploadPayload
from tgapp.domain.models import CorrectionFile, ProcessingSettings, SummaryResult, ThermogramFile, ThermogramViewSettings
from tgapp.domain.peaks import detect_peaks
from tgapp.domain.processing import process_thermograms
from tgapp.domain.summary import build_effect_text
from tgapp.infrastructure.file_parsers import decode_dash_upload, parse_correction_upload, parse_thermogram_uploads
from tgapp.infrastructure.plotting import build_raw_plot, figure_to_json
from tgapp.infrastructure.serialization import pack_session_directory, unpack_session_archive
from tgapp.infrastructure.storage import SessionStorage


def create_session(storage: SessionStorage) -> SessionStateDto:
    session_id = storage.create_session()
    return SessionStateDto(
        session_id=session_id,
        session_dir=str(storage.session_dir(session_id)),
        status="created",
        messages=[asdict(UiMessage(text=f"Session created: {session_id}"))],
    )


def _require_session_id(session_state: dict[str, object], storage: SessionStorage) -> str:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if isinstance(session_id, str) and session_id:
        return session_id
    return create_session(storage).session_id or storage.create_session()


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _list_of_str(value: object) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def load_thermograms(
    storage: SessionStorage,
    session_state: dict[str, object],
    uploads: list[UploadPayload],
) -> SessionStateDto:
    session_id = _require_session_id(session_state, storage)
    parsed = parse_thermogram_uploads(uploads)
    frames = {f"thermogram_{index + 1}.csv": item.frame for index, item in enumerate(parsed)}
    filenames = storage.save_thermograms(session_id, frames)
    storage.save_raw_thermograms(session_id, frames)
    metadata = {
        "original_names": [item.name for item in parsed],
        "status": "thermograms-loaded",
    }
    storage.save_json(storage.metadata_path(session_id), metadata)
    return SessionStateDto(
        session_id=session_id,
        session_dir=str(storage.session_dir(session_id)),
        thermogram_files=filenames,
        correction_file=_optional_str(session_state.get("correction_file")) if isinstance(session_state, dict) else None,
        imported_archive=_optional_str(session_state.get("imported_archive")) if isinstance(session_state, dict) else None,
        status="thermograms-loaded",
        messages=[asdict(UiMessage(text=f"Loaded {len(parsed)} thermogram file(s)."))],
    )


def load_correction(storage: SessionStorage, session_state: dict[str, object], upload: UploadPayload) -> SessionStateDto:
    session_id = _require_session_id(session_state, storage)
    correction = parse_correction_upload(upload)
    path = storage.save_frame(storage.correction_path(session_id), correction.frame)
    metadata = storage.load_json(storage.metadata_path(session_id))
    metadata["correction_original_name"] = correction.name
    metadata["status"] = "correction-loaded"
    storage.save_json(storage.metadata_path(session_id), metadata)
    return SessionStateDto(
        session_id=session_id,
        session_dir=str(storage.session_dir(session_id)),
        thermogram_files=_list_of_str(session_state.get("thermogram_files")) if isinstance(session_state, dict) else [],
        correction_file=path.name,
        imported_archive=_optional_str(session_state.get("imported_archive")) if isinstance(session_state, dict) else None,
        status="correction-loaded",
        messages=[asdict(UiMessage(text=f"Loaded correction file: {correction.name}"))],
    )


def import_saved_session(storage: SessionStorage, upload: UploadPayload) -> SessionStateDto:
    session = create_session(storage)
    decoded = decode_dash_upload(upload)
    archive_path = storage.session_dir(session.session_id or "") / "import.tg"
    archive_path.write_bytes(decoded.raw_bytes)
    unpack_session_archive(archive_path, storage.session_dir(session.session_id or ""))
    thermograms = [path.name for path in storage.thermogram_dir(session.session_id or "").glob("*.csv")]
    correction_name = storage.correction_path(session.session_id or "").name if storage.correction_path(session.session_id or "").exists() else None
    return SessionStateDto(
        session_id=session.session_id,
        session_dir=session.session_dir,
        thermogram_files=thermograms,
        correction_file=correction_name,
        imported_archive=decoded.filename,
        status="imported",
        messages=[asdict(UiMessage(text=f"Imported saved session: {decoded.filename}"))],
    )


def _load_thermogram_models(storage: SessionStorage, session_id: str) -> list[ThermogramFile]:
    return [ThermogramFile(name=name, frame=frame, source_kind="storage") for name, frame in storage.load_thermograms(session_id).items()]


def load_raw_plot_frame(storage: SessionStorage, session_state: dict[str, object]) -> pd.DataFrame:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return pd.DataFrame()

    raw_thermograms = storage.load_raw_thermograms(session_id)
    if raw_thermograms:
        return next(iter(raw_thermograms.values()))

    thermograms = storage.load_thermograms(session_id)
    if thermograms:
        return next(iter(thermograms.values()))

    return pd.DataFrame()


def get_visible_thermogram_plot_json(
    storage: SessionStorage,
    session_state: dict[str, object],
    settings: ThermogramViewSettings,
) -> str:
    return figure_to_json(build_raw_plot(load_raw_plot_frame(storage, session_state), settings))


def _load_correction_model(storage: SessionStorage, session_id: str) -> CorrectionFile | None:
    path = storage.correction_path(session_id)
    if not path.exists():
        return None
    return CorrectionFile(name=path.name, frame=storage.load_frame(path))


def process_session(storage: SessionStorage, session_state: dict[str, object], settings: ProcessingSettings) -> dict[str, object]:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "no-session"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}

    thermograms = _load_thermogram_models(storage, session_id)
    if not thermograms:
        return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "waiting-for-thermograms"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}

    correction = _load_correction_model(storage, session_id)
    processed = process_thermograms(thermograms, settings, correction)
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


def get_plot_payload(storage: SessionStorage, session_state: dict[str, object], settings: ProcessingSettings) -> PlotPayload:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return PlotPayload(settings=asdict(settings), title="Термограмма")

    processed = storage.load_frame(storage.processed_path(session_id))
    peaks = [asdict(peak) for peak in detect_peaks(processed, settings)] if not processed.empty else []
    return PlotPayload(frame_records=processed.to_dict("records"), peaks=peaks, settings=asdict(settings), title="Термограмма")


def get_summary(processing_state: dict[str, object]) -> SummaryResult:
    summary = processing_state.get("summary", {}) if isinstance(processing_state, dict) else {}
    lines = summary.get("lines", []) if isinstance(summary, dict) else []
    metrics = summary.get("metrics", {}) if isinstance(summary, dict) else {}
    return SummaryResult(lines=lines, metrics=metrics)


def get_heat_speed_text(processing_state: dict[str, object]) -> str:
    text = processing_state.get("heat_speed_text") if isinstance(processing_state, dict) else None
    return str(text) if text else "Скорость нагрева: недоступна"


def get_effect_text(
    storage: SessionStorage,
    session_state: dict[str, object],
    settings: ProcessingSettings,
    xmin: float | None,
    xmax: float | None,
) -> str:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return "Тепловой эффект: выделите температурный интервал"
    processed = storage.load_frame(storage.processed_path(session_id))
    return build_effect_text(processed, xmin, xmax, settings.init_mass)


def export_session_archive(storage: SessionStorage, session_state: dict[str, object]) -> Path | None:
    session_id = session_state.get("session_id") if isinstance(session_state, dict) else None
    if not isinstance(session_id, str) or not session_id:
        return None
    return pack_session_directory(storage.session_dir(session_id), storage.session_dir(session_id) / f"{session_id}.tg")
