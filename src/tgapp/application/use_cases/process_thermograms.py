from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from tgapp.application.ports import SessionRepository, ThermogramParser
from tgapp.domain.models import (
    CorrectionFile,
    CorrectionRangeError,
    DerivativeCalculationError,
    InvalidProcessingSettingsError,
    NoCommonRangeError,
    ProcessingSettings,
    ValidatedThermogram,
    validate_processing_settings,
)
from tgapp.domain.processing_engine import ProcessingEngine
from tgapp.domain.validator import validate_parsed
from tgapp.application._helpers import validated_to_df

# Recovery warnings (PLAN_AUDIT §18)
from tgapp.application.error_responses import recovery_warning

logger = logging.getLogger(__name__)


def _load_validated_thermograms(
    storage: SessionRepository,
    session_id: str,
) -> list[ValidatedThermogram]:
    """Load validated thermograms from storage and convert to ValidatedThermogram objects."""
    validated_frames = storage.load_validated_thermograms(session_id)
    result: list[ValidatedThermogram] = []
    for name, frame in validated_frames.items():
        if frame.empty:
            continue
        temp = frame["temp"].to_numpy(dtype=float)
        deltatemp = frame["deltatemp"].to_numpy(dtype=float) if "deltatemp" in frame.columns else None
        time = frame["time"].to_numpy(dtype=float)
        mass = frame["mass"].to_numpy(dtype=float)
        validated = ValidatedThermogram(
            name=name,
            temp=temp,
            deltatemp=deltatemp,
            time=time,
            mass=mass,
            metadata={},
        )
        result.append(validated)
    return result





def _build_recovery_warning(validated: list[ValidatedThermogram]) -> dict | None:
    """Build recovery warning if any validation removed/interpolated rows."""
    total_removed = 0
    total_interpolated = 0
    for v in validated:
        meta = v.metadata or {}
        total_removed += meta.get("rows_removed", 0)
        total_interpolated += meta.get("rows_interpolated", 0)
    if total_removed == 0 and total_interpolated == 0:
        return None
    # Use the last validated thermogram's range as the actual range
    last = validated[-1]
    actual_range = (float(last.temp.min()), float(last.temp.max()))
    # Check for narrowed range (multiple files with different ranges)
    if len(validated) > 1:
        all_mins = [float(v.temp.min()) for v in validated]
        all_maxs = [float(v.temp.max()) for v in validated]
        narrowed_range = (max(all_mins), min(all_maxs))
    else:
        narrowed_range = None
    return recovery_warning(
        rows_removed=total_removed,
        rows_interpolated=total_interpolated,
        actual_range=actual_range,
        narrowed_range=narrowed_range,
    ).to_dict()


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

    # Load validated thermograms (new pipeline)
    validated = _load_validated_thermograms(storage, session_id)
    if not validated:
        return {
            "settings": asdict(settings),
            "processed_ready": False,
            "summary": {"status": "no-valid-thermograms"},
            "heat_speed_text": "Скорость нагрева: недоступна",
            "effect_text": "Тепловой эффект: выделите температурный интервал",
            "error": {
                "message": "Нет валидированных термограмм для обработки.",
                "severity": "error",
                "details": "Загрузите и проверьте файлы термограмм. Файлы не прошли валидацию.",
            },
        }

    # New pipeline: align → process via ProcessingEngine
    # validated thermograms are already validated during upload (upload_thermograms.py)
    # Load correction file
    correction = _load_correction_model(storage, session_id)

    # Validate settings before processing
    validate_processing_settings(settings)

    # Run unified processing engine
    engine = ProcessingEngine(settings=settings)
    try:
        processed_result = engine.process(validated, settings=settings, correction=correction)
    except (CorrectionRangeError, DerivativeCalculationError, NoCommonRangeError, InvalidProcessingSettingsError) as e:
        logger.warning("Processing domain error: %s", e)
        return {
            "settings": asdict(settings),
            "processed_ready": False,
            "summary": {"status": "processing-error"},
            "heat_speed_text": "Скорость нагрева: недоступна",
            "effect_text": "Тепловой эффект: выделите температурный интервал",
            "error": {
                "message": str(e),
                "severity": "error",
                "details": "Проверьте данные и параметры обработки.",
            },
        }
    except Exception as e:
        logger.exception("Unexpected processing error")
        return {
            "settings": asdict(settings),
            "processed_ready": False,
            "summary": {"status": "internal-processing-error"},
            "heat_speed_text": "Скорость нагрева: недоступна",
            "effect_text": "Тепловой эффект: выделите температурный интервал",
            "error": {
                "message": "Произошла ошибка при обработке.",
                "severity": "error",
                "details": "Проверьте данные и параметры, затем повторите попытку.",
            },
        }

    # Save results to storage
    storage.save_frame(storage.processed_path(session_id), processed_result.derivatives)
    storage.save_frame(storage.raw_plot_path(session_id), processed_result.derivatives)
    storage.save_json(storage.settings_path(session_id), asdict(settings))
    metadata = storage.load_json(storage.metadata_path(session_id))
    metadata["last_process"] = {
        "heat_speed_text": processed_result.heat_speed_text,
        "peak_count": len(processed_result.peaks),
        "adjusted_difflag": settings.difflag,
        "summary": asdict(processed_result.summary),
    }
    metadata["status"] = "processed"
    storage.save_json(storage.metadata_path(session_id), metadata)
    result = {
        "settings": asdict(settings),
        "processed_ready": True,
        "summary": asdict(processed_result.summary),
        "heat_speed_text": processed_result.heat_speed_text,
        "effect_text": "Тепловой эффект: выделите температурный интервал",
    }
    recovery = _build_recovery_warning(validated)
    if recovery:
        result["recovery_warning"] = recovery
    return result