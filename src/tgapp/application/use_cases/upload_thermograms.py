from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tgapp.application.dto import SessionStateDto, UploadPayload, UiMessage
from tgapp.application.ports import SessionRepository, ThermogramParser


def create_session(storage: SessionRepository) -> SessionStateDto:
    session_id = storage.create_session()
    return SessionStateDto(
        session_id=session_id,
        session_dir=str(storage.session_dir(session_id)),
        status="created",
        messages=[asdict(UiMessage(text=f"Session created: {session_id}"))],
    )


def _require_session_id(session_state: dict[str, object], storage: SessionRepository) -> str:
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


def upload_thermograms(
    storage: SessionRepository,
    parser: ThermogramParser,
    session_state: dict[str, object],
    uploads: list[UploadPayload],
) -> SessionStateDto:
    session_id = _require_session_id(session_state, storage)
    parsed = parser.parse_thermogram_uploads(uploads)
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


def upload_correction(
    storage: SessionRepository,
    parser: ThermogramParser,
    session_state: dict[str, object],
    upload: UploadPayload,
) -> SessionStateDto:
    session_id = _require_session_id(session_state, storage)
    correction = parser.parse_correction_upload(upload)
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