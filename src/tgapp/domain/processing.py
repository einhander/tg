from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from tgapp.domain.models import CorrectionFile, PeakResult, ProcessingSettings, ThermogramFile, ThermogramProcessed
from tgapp.domain.peaks import detect_peaks
from tgapp.domain.smoothing import smooth_derivative, smooth_mass, smooth_mass_savitzky_golay, smooth_temperature
from tgapp.domain.summary import build_heat_speed_text, build_summary
from tgapp.domain.thermogram import combine_thermograms, compute_mean_correction, compute_mean_traces, resample_thermogram


def estimate_adjusted_difflag(resampled_times: list[pd.DataFrame], bins: int, difflag: int) -> int:
    time_arrays = [frame["time"].to_numpy(dtype=float) for frame in resampled_times if not frame.empty and "time" in frame.columns]
    if not time_arrays:
        return 1
    time_matrix = np.vstack(time_arrays)
    timediff = time_matrix.mean(axis=0)
    max_timediff = float(np.nanmax(timediff * 60.0)) if timediff.size else 0.0
    if max_timediff <= 0:
        return 1
    points = bins / max_timediff
    adjusted = int(round(difflag * points))
    return max(adjusted, 1)


def round_mean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rounded = frame.copy()
    for column in ("temp", "time", "deltatemp"):
        if column in rounded.columns:
            rounded[column] = rounded[column].round(2)
    if "mass" in rounded.columns:
        rounded["mass"] = rounded["mass"].round(3)
    return rounded


def compute_dmdt_trace(frame: pd.DataFrame, difflag: int, bins: int) -> pd.Series:
    if frame.empty or "mass" not in frame.columns or "time" not in frame.columns:
        return pd.Series([np.nan] * max(bins, 1), name="dmdt", dtype="float64")

    lag = max(int(difflag), 1)
    mass = frame["mass"].to_numpy(dtype=float)
    time = frame["time"].to_numpy(dtype=float)
    if len(mass) <= lag or len(time) <= lag:
        return pd.Series([np.nan] * len(frame.index), name="dmdt", dtype="float64")

    delta_mass = mass[lag:] - mass[:-lag]
    delta_time = time[lag:] - time[:-lag]
    dmdt = np.divide(delta_mass, delta_time, out=np.full_like(delta_mass, np.nan, dtype=float), where=np.abs(delta_time) > 1e-12)

    if len(dmdt) > 1 and len(dmdt) != bins:
        source_index = np.linspace(0.0, 1.0, num=len(dmdt))
        target_bins = max(int(bins - lag), 1)
        target_index = np.linspace(0.0, 1.0, num=target_bins)
        dmdt = np.interp(target_index, source_index, dmdt)

    padded = np.concatenate([dmdt, np.full(lag, np.nan)])
    padded = padded[: len(frame.index)] if len(padded) >= len(frame.index) else np.concatenate([padded, np.full(len(frame.index) - len(padded), np.nan)])
    return pd.Series(padded, name="dmdt", dtype="float64")


def process_thermograms(
    thermograms: list[ThermogramFile],
    settings: ProcessingSettings,
    correction: CorrectionFile | None = None,
) -> ThermogramProcessed:
    combined = combine_thermograms(thermograms)
    resampled = [resample_thermogram(item.frame, settings.bins) for item in thermograms]
    resampled = [frame for frame in resampled if not frame.empty]
    mean_frame = compute_mean_traces(resampled)
    adjusted_difflag = estimate_adjusted_difflag(resampled, settings.bins, settings.difflag)

    # Apply Savitzky-Golay smoothing to mass BEFORE computing derivative
    if settings.sg_mode:
        mean_frame = smooth_mass_savitzky_golay(mean_frame, settings.sg_window, settings.sg_polyorder)
    else:
        mean_frame = smooth_mass(mean_frame, settings.mass_smoothing)

    mean_frame["dmdt"] = compute_dmdt_trace(mean_frame, adjusted_difflag, settings.bins)

    if settings.use_correction:
        correction_mean = compute_mean_correction(correction, settings.bins)
        if correction_mean is not None and len(correction_mean) == len(mean_frame.index):
            mean_frame["deltatemp"] = mean_frame["deltatemp"].to_numpy(dtype=float) + correction_mean

    mean_frame = smooth_temperature(mean_frame, settings.temp_smoothing)
    mean_frame = smooth_derivative(mean_frame, settings.span, settings.smooth_dmdt)

    # Detect peaks on unrounded data for stable extrema detection
    peaks = detect_peaks(mean_frame, settings)

    # Round for output parity after analysis
    mean_frame = round_mean_frame(mean_frame)

    summary = build_summary(thermograms, mean_frame, peaks)
    heat_speed = build_heat_speed_text(mean_frame)
    return ThermogramProcessed(
        combined=combined,
        mass_smoothed=mean_frame.loc[:, [column for column in ("temp", "mass") if column in mean_frame.columns]].copy(),
        temp_smoothed=mean_frame.loc[:, [column for column in ("time", "temp", "deltatemp") if column in mean_frame.columns]].copy(),
        derivatives=mean_frame.copy(),
        mean_frame=mean_frame.copy(),
        peaks=peaks,
        summary=summary,
        heat_speed_text=heat_speed,
        adjusted_difflag=adjusted_difflag,
        metadata={"correction_loaded": correction is not None, "adjusted_difflag": adjusted_difflag, "settings": asdict(settings)},
    )
