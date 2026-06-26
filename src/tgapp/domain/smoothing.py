from __future__ import annotations

import numpy as np
import pandas as pd


def smooth_mass(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    smoothed = frame.copy()
    if "mass" in smoothed.columns and not smoothed.empty and window > 1:
        smoothed["mass"] = smoothed["mass"].rolling(max(window, 1), min_periods=1, center=True).mean()
    return smoothed


def smooth_mass_savitzky_golay(frame: pd.DataFrame, window: int, polyorder: int) -> pd.DataFrame:
    """Apply Savitzky-Golay filter to mass column. Preserves peak shapes for clean derivatives."""
    smoothed = frame.copy()
    if "mass" not in smoothed.columns or smoothed.empty:
        return smoothed

    mass = smoothed["mass"].to_numpy(dtype=float)
    n = len(mass)

    # Window must be odd and > polyorder
    win = max(window, 3)
    if win % 2 == 0:
        win += 1
    if win > n:
        win = n if n % 2 == 1 else n - 1
    if win < 3:
        return smoothed

    pord = min(max(polyorder, 1), win - 2)

    try:
        from scipy.signal import savgol_filter
        smoothed["mass"] = savgol_filter(mass, win, pord)
    except ImportError:
        # Fallback: weighted polynomial fit per window
        smoothed["mass"] = _savgol_fallback(mass, win, pord)
    except ValueError:
        pass

    return smoothed


def _savgol_fallback(y: np.ndarray, window: int, polyorder: int) -> np.ndarray:
    """Manual Savitzky-Golay when scipy is unavailable."""
    n = len(y)
    result = y.copy()
    half = window // 2

    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        x = np.arange(hi - lo, dtype=float)
        segment = y[lo:hi]
        try:
            coeffs = np.polyfit(x, segment, polyorder)
            result[i] = np.polyval(coeffs, x[len(segment) // 2])
        except np.linalg.LinAlgError:
            result[i] = y[i]

    return result


def smooth_temperature(frame: pd.DataFrame, window: int) -> pd.DataFrame:
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
