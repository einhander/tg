from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


def _finite_segments(values: np.ndarray) -> list[slice]:
    """Return slices of contiguous finite segments."""
    valid = np.isfinite(values)
    segments: list[slice] = []
    start = None
    for i, v in enumerate(valid):
        if v and start is None:
            start = i
        elif not v and start is not None:
            segments.append(slice(start, i))
            start = None
    if start is not None:
        segments.append(slice(start, len(values)))
    return segments


def _savgol_values(values: np.ndarray, window: int, polyorder: int, mode: str = "mirror") -> np.ndarray:
    """Apply Savitzky-Golay filter, processing finite segments independently.

    Args:
        values: input array (may contain NaN gaps)
        window: filter window size
        polyorder: polynomial order
        mode: filter mode passed to scipy.signal.savgol_filter

    Returns:
        Smoothed array, NaN gaps preserved
    """
    n = len(values)
    if n < 3:
        return values.copy()

    # Validate window
    win = window
    if win % 2 == 0:
        raise ValueError(f"Сavitzky-Golay window must be odd, got {win}")
    if win < 3:
        return values.copy()
    if win > n:
        raise ValueError(f"Сavitzky-Golay window {win} exceeds array length {n}")

    pord = min(max(polyorder, 1), win - 2)

    segments = _finite_segments(values)
    result = values.copy()

    for seg in segments:
        seg_len = seg.stop - seg.start
        if seg_len < 3:
            # Segment too short, skip smoothing
            continue
        if win > seg_len:
            # Window larger than segment, skip
            continue

        seg_values = values[seg]
        try:
            from scipy.signal import savgol_filter
            filtered = savgol_filter(seg_values, win, pord, mode=mode)
            result[seg] = filtered
        except ValueError:
            # If scipy fails, leave segment unchanged
            pass

    return result


def smooth_mass(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    smoothed = frame.copy()
    if "mass" in smoothed.columns and not smoothed.empty and window > 1:
        smoothed["mass"] = smoothed["mass"].rolling(max(window, 1), min_periods=1, center=True).mean()
    return smoothed


def smooth_series_savitzky_golay(series: pd.Series, window: int, polyorder: int = 3) -> pd.Series:
    """Apply Savitzky-Golay filter to one numeric series while preserving NaN gaps."""
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    valid = np.isfinite(values)
    if valid.sum() < 3:
        return numeric

    smoothed = numeric.copy()
    try:
        filtered = _savgol_values(values[valid], window, polyorder)
        smoothed.loc[valid] = filtered
    except ValueError as e:
        # If validation fails, return original
        return numeric
    return smoothed


def smooth_column_savitzky_golay(frame: pd.DataFrame, column: str, window: int, polyorder: int, mode: str = "mirror") -> pd.DataFrame:
    """Apply Savitzky-Golay filter to one frame column.

    Validates parameters strictly. Raises ValueError on invalid params.
    """
    smoothed = frame.copy()
    if column not in smoothed.columns or smoothed.empty:
        return smoothed

    # Validate parameters
    if window % 2 == 0:
        raise ValueError(f"Сavitzky-Golay window must be odd, got {window}")
    if polyorder < 1:
        raise ValueError(f"Сavitzky-Golay polyorder must be >= 1, got {polyorder}")
    if polyorder >= window:
        raise ValueError(f"Сavitzky-Golay polyorder ({polyorder}) must be less than window ({window})")

    smoothed[column] = smooth_series_savitzky_golay(smoothed[column], window, polyorder)
    return smoothed


def smooth_mass_savitzky_golay(frame: pd.DataFrame, window: int, polyorder: int) -> pd.DataFrame:
    """Apply Savitzky-Golay filter to mass column. Preserves peak shapes for clean derivatives."""
    return smooth_column_savitzky_golay(frame, "mass", window, polyorder)


def smooth_temperature_savitzky_golay(frame: pd.DataFrame, window: int, polyorder: int = 3) -> pd.DataFrame:
    """DEPRECATED: Temperature smoothing is no longer applied in the scientific pipeline."""
    warnings.warn(
        "smooth_temperature_savitzky_golay is deprecated. "
        "Physical axes (temperature, time) must not be smoothed.",
        DeprecationWarning,
        stacklevel=2,
    )
    return smooth_column_savitzky_golay(frame, "temp", window, polyorder)


def smooth_derivative_savitzky_golay(frame: pd.DataFrame, window: int, polyorder: int = 3) -> pd.DataFrame:
    """Savitzky-Golay smoothing for DTG (dmdt) column."""
    return smooth_column_savitzky_golay(frame, "dmdt", window, polyorder)


def smooth_temperature(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """DEPRECATED: Temperature smoothing is no longer applied in the scientific pipeline."""
    warnings.warn(
        "smooth_temperature is deprecated. "
        "Physical axes (temperature, time) must not be smoothed.",
        DeprecationWarning,
        stacklevel=2,
    )
    smoothed = frame.copy()
    if "temp" in smoothed.columns and not smoothed.empty and window > 1:
        smoothed["temp"] = smoothed["temp"].rolling(max(window, 1), min_periods=1, center=True).mean()
    return smoothed


def smooth_derivative(frame: pd.DataFrame, span: float, enabled: bool) -> pd.DataFrame:
    smoothed = frame.copy()
    if "dmdt" in smoothed.columns and enabled and not smoothed.empty:
        valid = smoothed.loc[:, [column for column in ("temp", "dmdt") if column in smoothed.columns]].dropna().reset_index()
        if len(valid.index) >= 3:
            smoothed_values = _smooth_spline_like(
                valid["temp"].to_numpy(dtype=float),
                valid["dmdt"].to_numpy(dtype=float),
                span,
            )
            smoothed.loc[valid["index"].to_numpy(dtype=int), "dmdt"] = smoothed_values
    return smoothed


def _smooth_spline_like(x: np.ndarray, y: np.ndarray, span: float) -> np.ndarray:
    bandwidth = _bandwidth_from_span(len(x), span)
    if bandwidth <= 1:
        return y.copy()

    smoothed = np.empty_like(y, dtype=float)
    for index, center in enumerate(x):
        distances = np.abs(x - center)
        radius = float(np.partition(distances, min(bandwidth - 1, len(distances) - 1))[min(bandwidth - 1, len(distances) - 1)])
        radius = max(radius, 1e-12)
        weights = np.clip(1.0 - (distances / radius) ** 3, 0.0, None) ** 3
        x_shifted = x - center
        design = np.column_stack((np.ones_like(x_shifted), x_shifted, x_shifted**2))
        weighted_design = design * weights[:, None]
        try:
            coeffs, *_ = np.linalg.lstsq(weighted_design, y * weights, rcond=None)
            smoothed[index] = float(coeffs[0])
        except np.linalg.LinAlgError:
            smoothed[index] = y[index]
    return smoothed


def _bandwidth_from_span(length: int, span: float) -> int:
    if length < 3:
        return 1
    inverted = max(100.0 - float(span), 1.0)
    window = int(round(length * inverted / 100.0))
    return min(max(window, 3), length)
