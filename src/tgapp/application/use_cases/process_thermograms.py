from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from tgapp.application.ports import SessionRepository, ThermogramParser
from tgapp.domain.models import (
    CorrectionFile,
    ProcessingSettings,
    ThermogramFile,
    ValidatedThermogram,
)
from tgapp.domain.processing import process_thermograms as _domain_process
from tgapp.domain.processing_engine import ProcessingEngine
from tgapp.domain.validator import validate_parsed

# Recovery warnings (PLAN_AUDIT §18)
from tgapp.application.error_responses import recovery_warning

logger = logging.getLogger(__name__)


def _load_thermogram_models(storage: SessionRepository, session_id: str) -> list[ThermogramFile]:
    return [ThermogramFile(name=name, frame=frame, source_kind="storage") for name, frame in storage.load_thermograms(session_id).items()]


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


def _validated_to_df(v: ValidatedThermogram) -> pd.DataFrame:
    """Convert ValidatedThermogram back to DataFrame for storage."""
    data: dict[str, list[float]] = {
        "temp": v.temp.tolist(),
        "time": v.time.tolist(),
        "mass": v.mass.tolist(),
    }
    if v.deltatemp is not None:
        data["deltatemp"] = v.deltatemp.tolist()
    return pd.DataFrame(data)


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
        # Fallback: load from legacy ThermogramFile storage
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
        result = {
            "settings": asdict(settings),
            "processed_ready": True,
            "summary": asdict(processed.summary),
            "heat_speed_text": processed.heat_speed_text,
            "effect_text": "Тепловой эффект: выделите температурный интервал",
        }
        recovery = _build_recovery_warning(validated)
        if recovery:
            result["recovery_warning"] = recovery
        return result

    # New pipeline: validate → align → process via ProcessingEngine
    # Re-validate loaded validated thermograms (defensive)
    re_validated: list[ValidatedThermogram] = []
    for v in validated:
        try:
            rv = validate_parsed(v.temp, v.deltatemp, v.time, v.mass)
            rv = ValidatedThermogram(
                name=v.name,
                temp=rv.temp,
                deltatemp=rv.deltatemp,
                time=rv.time,
                mass=rv.mass,
                metadata=rv.metadata,
            )
            re_validated.append(rv)
        except Exception as e:
            logger.warning("Validation failed for %s: %s", v.name, e)
            continue

    if not re_validated:
        return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "no-valid-thermograms"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}

    # Load correction file
    correction = _load_correction_model(storage, session_id)

    # Run unified processing engine
    engine = ProcessingEngine(settings=settings)
    try:
        processed_result = engine.process(re_validated, settings=settings, correction=correction)
    except Exception as e:
        logger.warning("ProcessingEngine failed, falling back to legacy: %s", e)
        thermograms = _load_thermogram_models(storage, session_id)
        if not thermograms:
            return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "no-thermograms"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}
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
        result = {
            "settings": asdict(settings),
            "processed_ready": True,
            "summary": asdict(processed.summary),
            "heat_speed_text": processed.heat_speed_text,
            "effect_text": "Тепловой эффект: выделите температурный интервал",
        }
        recovery = _build_recovery_warning(re_validated)
        if recovery:
            result["recovery_warning"] = recovery
        return result

    # Save results to storage
    storage.save_frame(storage.processed_path(session_id), processed_result.mean_frame)
    storage.save_frame(storage.raw_plot_path(session_id), processed_result.mean_frame)
    storage.save_json(storage.settings_path(session_id), asdict(settings))
    metadata = storage.load_json(storage.metadata_path(session_id))
    metadata["last_process"] = {
        "heat_speed_text": processed_result.heat_speed_text,
        "peak_count": len(processed_result.peaks),
        "adjusted_difflag": 1,
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
    recovery = _build_recovery_warning(re_validated)
    if recovery:
        result["recovery_warning"] = recovery
    return result