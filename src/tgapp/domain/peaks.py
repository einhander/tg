from __future__ import annotations

import numpy as np
import pandas as pd

from tgapp.domain.models import PeakResult, ProcessingSettings, ThermogramViewSettings


# Default prominence threshold in noise-sigma units.
# Peaks with prominence below this threshold are treated as noise.
DEFAULT_PROMINENCE_SIGMA = 5.0

# Window for noise estimation (rolling mean to extract signal)
_NOISE_WINDOW = 11


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
    """Estimate noise sigma from high-frequency residual using MAD.

    Uses a simple rolling mean to extract signal, then measures the
    median absolute deviation of the residual. No external dependencies.
    """
    n = len(y)
    if n < _NOISE_WINDOW + 2:
        return float(np.std(y)) if n > 1 else 0.0

    # Extract signal via rolling mean (numpy-only, no scipy)
    cumsum = np.cumsum(np.insert(y, 0, 0))
    signal = (cumsum[_NOISE_WINDOW:] - cumsum[:-_NOISE_WINDOW]) / _NOISE_WINDOW
    # Align lengths: rolling mean is shorter by (window - 1)
    align = (_NOISE_WINDOW - 1) // 2
    residual = y[align:align + len(signal)] - signal

    # MAD-based sigma estimate (robust to outliers)
    mad = float(np.median(np.abs(residual - np.median(residual))))
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
    min_prominence = prominence_sigma * noise_sigma if noise_sigma > 0 else 0.0

    results: list[PeakResult] = []
    for index in range(window, len(valid.index) - window):
        segment = valid.iloc[index - window : index + window + 1]
        center_y = float(valid.iloc[index][y_column])
        center_x = float(valid.iloc[index]["temp"])
        segment_max = float(segment[y_column].max())
        segment_min = float(segment[y_column].min())

        left_y = float(valid.iloc[index - 1][y_column])
        right_y = float(valid.iloc[index + 1][y_column])
        local_range = segment_max - segment_min

        if (
            center_y == segment_max
            and center_y >= left_y
            and center_y > right_y
            and local_range > 0
        ):
            prominence = abs(center_y - segment_min)
            if prominence >= min_prominence:
                results.append(PeakResult(x=center_x, y=center_y, label=f"{center_x:.1f}", kind=trace_kind, extremum="peak"))
        elif (
            center_y == segment_min
            and center_y <= left_y
            and center_y < right_y
            and local_range > 0
        ):
            prominence = abs(center_y - segment_max)
            if prominence >= min_prominence:
                results.append(PeakResult(x=center_x, y=center_y, label=f"{center_x:.1f}", kind=trace_kind, extremum="valley"))

    return _dedupe_extrema(results, window)


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


def _dedupe_extrema(results: list[PeakResult], window: int) -> list[PeakResult]:
    if not results:
        return []
    sorted_peaks = sorted(results, key=lambda item: (item.kind, item.extremum, item.x))
    if len(sorted_peaks) >= 2:
        x_spacing = (sorted_peaks[-1].x - sorted_peaks[0].x) / max(len(sorted_peaks) - 1, 1)
    else:
        x_spacing = 1.0

    deduped: list[PeakResult] = []
    min_distance = max(window, 1) * max(x_spacing, 0.0)
    for peak in sorted_peaks:
        if not deduped:
            deduped.append(peak)
            continue
        previous = deduped[-1]
        same_group = (
            previous.kind == peak.kind
            and previous.extremum == peak.extremum
            and abs(previous.x - peak.x) <= min_distance
        )
        if same_group:
            if abs(peak.y) >= abs(previous.y):
                deduped[-1] = peak
        else:
            deduped.append(peak)
    return deduped


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
