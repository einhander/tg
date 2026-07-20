from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from tgapp.application.ports import SessionRepository, ThermogramParser
from tgapp.domain.alignment import align_thermograms
from tgapp.domain.correction import apply_correction_to_aligned
from tgapp.domain.models import (
    AlignedThermogram,
    CorrectionFile,
    ProcessingSettings,
    ThermogramFile,
    ValidatedThermogram,
)
from tgapp.domain.processing import process_thermograms as _domain_process
from tgapp.domain.validator import validate_parsed

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
        return {
            "settings": asdict(settings),
            "processed_ready": True,
            "summary": asdict(processed.summary),
            "heat_speed_text": processed.heat_speed_text,
            "effect_text": "Тепловой эффект: выделите температурный интервал",
        }

    # New pipeline: validate → align → process
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

    # Align thermograms on common temperature grid
    try:
        aligned = align_thermograms(re_validated, bins=settings.bins)
    except Exception:
        # Fallback to legacy pipeline if alignment fails
        thermograms = _load_thermogram_models(storage, session_id)
        if not thermograms:
            return {"settings": asdict(settings), "processed_ready": False, "summary": {"status": "no-thermograms"}, "heat_speed_text": "Скорость нагрева: недоступна", "effect_text": "Тепловой эффект: выделите температурный интервал"}
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

    # Apply temperature correction to aligned thermograms (temperature-grid interpolation)
    corrected_aligned = aligned
    correction = _load_correction_model(storage, session_id)
    if settings.use_correction and correction is not None:
        try:
            corrected_aligned = apply_correction_to_aligned(aligned, correction)
        except Exception as e:
            logger.warning("Correction skipped: %s", e)

    # Build ThermogramFile objects from aligned (corrected) thermograms for domain processing
    aligned_thermograms: list[ThermogramFile] = []
    for a in corrected_aligned:
        data: dict[str, list[float]] = {
            "temp": a.temp.tolist(),
            "time": a.time.tolist(),
            "mass": a.mass.tolist(),
        }
        if a.deltatemp is not None:
            data["deltatemp"] = a.deltatemp.tolist()
        aligned_thermograms.append(ThermogramFile(name=a.name, frame=pd.DataFrame(data)))

    processed = _domain_process(aligned_thermograms, settings, correction)
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