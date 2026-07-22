from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from tgapp.application.dto import SessionStateDto, UploadPayload, UiMessage
from tgapp.application.ports import SessionRepository, ThermogramParser
from tgapp.domain.models import ParsedThermogram, ThermogramFile, UploadedThermogramResult, ValidatedThermogram
from tgapp.domain.validator import validate_parsed
from tgapp.application._helpers import validated_to_df

logger = logging.getLogger(__name__)


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
    parsed_files = parser.parse_thermogram_uploads(uploads)

    # Track per-file validation results
    file_results: list[UploadedThermogramResult] = []
    validated_frames: dict[str, pd.DataFrame] = {}

    for index, parsed_file in enumerate(parsed_files):
        parsed = parser.frame_to_parsed(parsed_file.name, parsed_file.frame, parsed_file.metadata.get("content_type", ""))
        parsed_rows = len(parsed.temp) if parsed.temp is not None else 0

        if parsed_rows == 0:
            file_results.append(UploadedThermogramResult(
                original_name=parsed_file.name,
                accepted=False,
                stored_name=None,
                parsed_rows=0,
                validated_rows=0,
                rows_removed=0,
                rows_interpolated=0,
                errors=("Файл не содержит данных после парсинга.",),
            ))
            continue

        try:
            validated = validate_parsed(parsed.temp, parsed.deltatemp, parsed.time, parsed.mass)
            validated = ValidatedThermogram(
                name=parsed_file.name,
                temp=validated.temp,
                deltatemp=validated.deltatemp,
                time=validated.time,
                mass=validated.mass,
                metadata=validated.metadata,
            )
            validated_df = validated_to_df(validated)
            validated_key = f"validated_thermogram_{index + 1}.csv"
            validated_frames[validated_key] = validated_df

            file_results.append(UploadedThermogramResult(
                original_name=parsed_file.name,
                accepted=True,
                stored_name=validated_key,
                parsed_rows=parsed_rows,
                validated_rows=len(validated.temp),
                rows_removed=validated.metadata.get("rows_removed", 0),
                rows_interpolated=validated.metadata.get("rows_interpolated", 0),
                warnings=(),
                errors=(),
            ))
        except Exception as e:
            logger.warning("Validation failed for %s: %s", parsed_file.name, e)
            file_results.append(UploadedThermogramResult(
                original_name=parsed_file.name,
                accepted=False,
                stored_name=None,
                parsed_rows=parsed_rows,
                validated_rows=0,
                rows_removed=0,
                rows_interpolated=0,
                errors=(str(e),),
            ))

    # Save validated thermograms
    storage.save_validated_thermograms(session_id, validated_frames)

    # Calculate summary stats
    accepted_count = sum(1 for r in file_results if r.accepted)
    rejected_count = sum(1 for r in file_results if not r.accepted)

    # Determine status
    if accepted_count == 0:
        status = "thermograms-not-accepted"
    elif rejected_count > 0:
        status = "thermograms-partially-loaded"
    else:
        status = "thermograms-loaded"

    # Build metadata with per-file results
    metadata = {
        "original_names": [item.name for item in parsed_files],
        "status": status,
        "file_results": [asdict(r) for r in file_results],
        "accepted_count": accepted_count,
        "rejected_count": rejected_count,
    }
    storage.save_json(storage.metadata_path(session_id), metadata)

    # Build user message
    if accepted_count == 0:
        msg = f"Загружено файлов: {len(parsed_files)}. Принято к обработке: 0. Отклонено: {rejected_count}."
        for r in file_results:
            if not r.accepted and r.errors:
                msg += f"\n{r.original_name}: {r.errors[0]}"
    elif rejected_count > 0:
        msg = f"Загружено файлов: {len(parsed_files)}. Принято к обработке: {accepted_count}. Отклонено: {rejected_count}."
        for r in file_results:
            if not r.accepted and r.errors:
                msg += f"\n{r.original_name}: {r.errors[0]}"
    else:
        msg = f"Загружено файлов: {len(parsed_files)}. Принято к обработке: {accepted_count}."

    return SessionStateDto(
        session_id=session_id,
        session_dir=str(storage.session_dir(session_id)),
        thermogram_files=list(validated_frames.keys()) if validated_frames else [],
        correction_file=_optional_str(session_state.get("correction_file")) if isinstance(session_state, dict) else None,
        imported_archive=_optional_str(session_state.get("imported_archive")) if isinstance(session_state, dict) else None,
        status=status,
        messages=[asdict(UiMessage(text=msg))],
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