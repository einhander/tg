from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd

from tgapp.domain.models import CorrectionFile, PeakResult, ProcessingSettings, ThermogramFile, ThermogramProcessed
from tgapp.domain.peaks import detect_peaks
from tgapp.domain.smoothing import (
    smooth_column_savitzky_golay,
    smooth_derivative,
    smooth_derivative_savitzky_golay,
    smooth_mass,
    smooth_temperature,
    smooth_temperature_savitzky_golay,
)
from tgapp.domain.summary import build_heat_speed_text, build_summary
from tgapp.domain.thermogram import combine_thermograms, compute_mean_correction, compute_mean_traces, resample_thermogram


def round_mean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    rounded = frame.copy()
    for column in ("temp", "time", "deltatemp"):
        if column in rounded.columns:
            rounded[column] = rounded[column].round(2)
    if "mass" in rounded.columns:
        rounded["mass"] = rounded["mass"].round(3)
    return rounded


def compute_dmdt_per_run(frame: pd.DataFrame) -> pd.Series:
    """Рассчитать dm/dt для одного эксперимента через np.gradient.

    Использует центральные разности (np.gradient), которые дают
    производную второго порядка точности.

    Args:
        frame: DataFrame с колонками 'mass' и 'time'

    Returns:
        Series с dm/dt в единицах массы/время
    """
    if frame.empty or "mass" not in frame.columns or "time" not in frame.columns:
        return pd.Series([np.nan] * 500, name="dmdt", dtype="float64")

    mass = frame["mass"].to_numpy(dtype=float)
    time = frame["time"].to_numpy(dtype=float)

    dmdt = np.gradient(mass, time)

    return pd.Series(dmdt, name="dmdt", dtype="float64", index=frame.index)


def average_dmdt_traces(dmdt_traces: list[pd.Series]) -> pd.Series:
    """Усреднить производные от нескольких экспериментов.

    Все серии должны иметь одинаковую длину (после выравнивания на общую сетку).

    Args:
        dmdt_traces: список серий с dm/dt от каждого эксперимента

    Returns:
        Одна усреднённая серия
    """
    if not dmdt_traces:
        return pd.Series([np.nan] * 500, name="dmdt", dtype="float64")

    lengths = {len(t) for t in dmdt_traces}
    if len(lengths) != 1:
        max_len = max(len(t) for t in dmdt_traces)
        aligned = []
        for t in dmdt_traces:
            if len(t) == max_len:
                aligned.append(t)
            else:
                old_idx = np.linspace(0, max_len - 1, len(t))
                new_idx = np.linspace(0, max_len - 1, max_len)
                aligned.append(pd.Series(
                    np.interp(new_idx, old_idx, t.to_numpy(dtype=float)),
                    name="dmdt",
                    dtype="float64",
                ))
        dmdt_traces = aligned

    stacked = np.stack([t.to_numpy(dtype=float) for t in dmdt_traces], axis=0)
    mean_dmdt = np.nanmean(stacked, axis=0)

    return pd.Series(mean_dmdt, name="dmdt", dtype="float64")


def process_thermograms(
    thermograms: list[ThermogramFile],
    settings: ProcessingSettings,
    correction: CorrectionFile | None = None,
) -> ThermogramProcessed:
    combined = combine_thermograms(thermograms)
    resampled = [resample_thermogram(item.frame, settings.bins) for item in thermograms]
    resampled = [frame for frame in resampled if not frame.empty]

    # Smooth each experiment individually BEFORE computing derivatives
    smoothed_frames = []
    for frame in resampled:
        if settings.sg_mode:
            smoothed = smooth_column_savitzky_golay(frame, "mass", settings.sg_window, settings.sg_polyorder)
        else:
            smoothed = smooth_mass(frame, settings.mass_smoothing)
        smoothed_frames.append(smoothed)

    # Calculate dm/dt for each experiment
    dmdt_traces = [compute_dmdt_per_run(frame) for frame in smoothed_frames]

    # Average derivatives
    mean_frame = compute_mean_traces(resampled)
    mean_dmdt = average_dmdt_traces(dmdt_traces)
    mean_frame["dmdt"] = mean_dmdt

    if settings.use_correction:
        correction_mean = compute_mean_correction(correction, settings.bins)
        if correction_mean is not None and len(correction_mean) == len(mean_frame.index):
            mean_frame["deltatemp"] = mean_frame["deltatemp"].to_numpy(dtype=float) + correction_mean

    if settings.sg_mode:
        mean_frame = smooth_column_savitzky_golay(mean_frame, "deltatemp", settings.sg_window, settings.sg_polyorder)

    # SG smoothing for temperature if enabled
    if settings.sg_mode:
        mean_frame = smooth_temperature_savitzky_golay(mean_frame, settings.sg_window, settings.sg_polyorder)
    else:
        mean_frame = smooth_temperature(mean_frame, settings.temp_smoothing)

    # SG smoothing for derivative if enabled
    if settings.sg_mode:
        mean_frame = smooth_derivative_savitzky_golay(mean_frame, settings.sg_window, settings.sg_polyorder)
    else:
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
        adjusted_difflag=1,
        metadata={"correction_loaded": correction is not None, "settings": asdict(settings)},
    )
