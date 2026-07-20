from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import find_peaks

from tgapp.domain.models import PeakResult, ProcessingSettings, ThermogramViewSettings


# Default prominence threshold in noise-sigma units.
# Peaks with prominence below this threshold are treated as noise.
DEFAULT_PROMINENCE_SIGMA = 5.0


def _window_from_span(length: int, span: float) -> int:
    if length < 3:
        return 1
    raw_window = (2 * round((((100.0 - min(max(span, 1.0), 100.0)) * length) / 100.0) / 2.0)) - 1
    window = max(int(raw_window), 3)
    if window % 2 == 0:
        window -= 1
    return min(window, length if length % 2 == 1 else length - 1)


def _half_window(length: int, span: float) -> int:
    return max((_window_from_span(length, span) - 1) // 2, 1)


def _raw_half_window(length: int) -> int:
    if length < 5:
        return 1
    window = max(length // 40, 2)
    return min(window, max((length - 1) // 2, 1))


def _estimate_noise_sigma(y: np.ndarray) -> float:
    """Estimate noise sigma using robust MAD on the raw signal.

    sigma = 1.4826 * median(|y - median(y)|)
    """
    n = len(y)
    if n < 2:
        return 0.0
    mad = float(np.median(np.abs(y - np.median(y))))
    return 1.4826 * mad


def _detect_extrema_points(
    valid: pd.DataFrame,
    y_column: str,
    trace_kind: str,
    window: int,
    prominence_sigma: float,
) -> list[PeakResult]:
    if len(valid.index) < 3:
        return []

    y_values = valid[y_column].to_numpy(dtype=float)

    noise_sigma = _estimate_noise_sigma(y_values)
    prominence = prominence_sigma * noise_sigma if noise_sigma > 0 else 0.0

    results: list[PeakResult] = []

    # Peaks: local maxima above prominence threshold
    peak_indices, peak_props = find_peaks(y_values, prominence=prominence)
    for idx in peak_indices:
        x = float(valid.iloc[idx]["temp"])
        y = float(y_values[idx])
        results.append(PeakResult(x=x, y=y, label=f"{x:.1f}", kind=trace_kind, extremum="peak"))

    # Valleys: local minima (find peaks on inverted signal)
    valley_indices, valley_props = find_peaks(-y_values, prominence=prominence)
    for idx in valley_indices:
        x = float(valid.iloc[idx]["temp"])
        y = float(y_values[idx])
        results.append(PeakResult(x=x, y=y, label=f"{x:.1f}", kind=trace_kind, extremum="valley"))

    return results


def detect_trace_extrema(
    frame: pd.DataFrame,
    y_column: str,
    trace_kind: str,
    span: float,
    prominence_sigma: float = DEFAULT_PROMINENCE_SIGMA,
) -> list[PeakResult]:
    if frame.empty or "temp" not in frame.columns or y_column not in frame.columns:
        return []

    valid = frame.loc[:, ["temp", y_column]].dropna().reset_index(drop=True)
    if len(valid.index) < 3:
        return []

    window = _half_window(len(valid.index), span)
    return _detect_extrema_points(valid, y_column, trace_kind, window, prominence_sigma)


def detect_peaks(frame: pd.DataFrame, settings: ProcessingSettings) -> list[PeakResult]:
    peaks: list[PeakResult] = []
    peak_sigma = settings.peak_prominence_sigma
    peaks.extend(detect_trace_extrema(frame, "deltatemp", "dta", settings.span, peak_sigma))
    peaks.extend(detect_trace_extrema(frame, "dmdt", "dtg", settings.span, peak_sigma))
    return peaks


def detect_tg_inflection_markers(frame: pd.DataFrame, peak_prominence_sigma: float, window: int | None = None) -> list[PeakResult]:
    if frame.empty or not {"temp", "mass"}.issubset(frame.columns):
        return []

    valid_mass = frame.loc[:, ["temp", "mass"]].dropna().reset_index(drop=True)
    if len(valid_mass.index) < 5:
        return []

    temp = valid_mass["temp"].to_numpy(dtype=float)
    mass = valid_mass["mass"].to_numpy(dtype=float)
    if np.any(np.diff(temp) <= 0):
        slope = np.gradient(mass)
    else:
        slope = np.gradient(mass, temp)
    slope_frame = pd.DataFrame({"temp": temp, "slope": slope, "mass": mass})
    detection_window = window if window is not None else _raw_half_window(len(slope_frame.index))
    slope_markers = _detect_extrema_points(slope_frame, "slope", "tg", min(detection_window, max(len(slope_frame.index) // 2, 1)), peak_prominence_sigma)
    for marker in slope_markers:
        marker_index = int(np.argmin(np.abs(temp - marker.x)))
        marker.y = float(mass[marker_index])
        marker.extremum = "inflection"
    return slope_markers


def detect_raw_plot_markers(frame: pd.DataFrame, settings: ThermogramViewSettings) -> list[PeakResult]:
    if frame.empty or "temp" not in frame.columns:
        return []

    markers: list[PeakResult] = []
    peak_sigma = settings.peak_prominence_sigma
    window = _raw_half_window(len(frame.index))

    if "deltatemp" in frame.columns:
        valid_dta = frame.loc[:, ["temp", "deltatemp"]].dropna().reset_index(drop=True)
        markers.extend(_detect_extrema_points(valid_dta, "deltatemp", "dta", min(window, max(len(valid_dta.index) // 2, 1)), peak_sigma))

    if "dmdt" in frame.columns:
        valid_dtg = frame.loc[:, ["temp", "dmdt"]].dropna().reset_index(drop=True)
        markers.extend(_detect_extrema_points(valid_dtg, "dmdt", "dtg", min(window, max(len(valid_dtg.index) // 2, 1)), peak_sigma))

    markers.extend(detect_tg_inflection_markers(frame, peak_sigma, window))

    return markers