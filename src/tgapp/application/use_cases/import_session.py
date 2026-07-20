from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from tgapp.application.dto import SessionStateDto, UploadPayload, UiMessage
from tgapp.application.ports import DecodedUpload, SessionArchiveService, SessionRepository, ThermogramParser


def import_session(
    storage: SessionRepository,
    archive_service: SessionArchiveService,
    parser: ThermogramParser,
    upload: UploadPayload,
) -> SessionStateDto:
    # Inline create_session logic to avoid circular import
    session_id = storage.create_session()
    session_dir = storage.session_dir(session_id)

    decoded = parser.decode_upload(upload)
    archive_path = session_dir / "import.tg"
    archive_path.write_bytes(decoded.raw_bytes)
    archive_service.unpack_session_archive(archive_path, session_dir)
    thermograms = [path.name for path in storage.thermogram_dir(session_id).glob("*.csv")]
    validated_thermograms = [path.name for path in storage.validated_thermogram_dir(session_id).glob("*.csv")]
    correction_name = storage.correction_path(session_id).name if storage.correction_path(session_id).exists() else None
    return SessionStateDto(
        session_id=session_id,
        session_dir=str(session_dir),
        thermogram_files=thermograms,
        validated_thermograms=validated_thermograms,
        correction_file=correction_name,
        imported_archive=decoded.filename,
        status="imported",
        messages=[asdict(UiMessage(text=f"Imported saved session: {decoded.filename}"))],
    )