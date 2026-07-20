"""Thermal effect calculation per PLAN_AUDIT §12.

Algorithm:
1. Normalize xmin/xmax boundaries without rounding to integer degrees
2. Sort data by temperature
3. Interpolate DTA values exactly at both boundaries
4. Add boundary points to the selected interval
5. Build linear baseline between signal values at boundaries
6. Integrate: integral(DTA(T) - baseline(T)) dT
7. Apply calibration coefficient only after documenting its meaning
8. Divide by initial mass with validation
"""

from __future__ import annotations

import logging
from typing import cast

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Calibration coefficient origin: zinc melting point calibration
# Value 0.4458333 converts instrument units (mV·min) to energy units (J/g)
# This is a CALIBRATION FACTOR, not a physical constant.
# The true thermal effect = raw_integral / (mass * calibration_factor)
# where calibration_factor depends on instrument sensitivity.
# For now, treat it as a documented calibration coefficient.
EFFECT_SCALE_K = 0.4458333


def calculate_thermal_effect(
    frame: pd.DataFrame,
    xmin: float,
    xmax: float,
    init_mass: float,
) -> str:
    """Calculate thermal effect for a temperature range.

    Args:
        frame: DataFrame with 'temp' and 'deltatemp' columns
        xmin: lower temperature boundary (not rounded)
        xmax: upper temperature boundary (not rounded)
        init_mass: initial mass in grams

    Returns:
        Formatted result string
    """
    if frame.empty or not {"temp", "deltatemp"}.issubset(frame.columns):
        return "Тепловой эффект: выделите температурный интервал"

    if init_mass < 0:
        return "Тепловой эффект: начальная масса должна быть положительной"

    if init_mass == 0:
        return "Тепловой эффект: начальная масса должна быть ненулевой"

    left, right = sorted((float(xmin), float(xmax)))
    if left == right:
        return "Тепловой эффект: выделите температурный интервал"

    # Step 2: Sort by temperature and drop NaN
    selection = frame.loc[:, ["temp", "deltatemp"]].dropna()
    selection = selection.sort_values("temp")

    if len(selection) < 2:
        return "Тепловой эффект: слишком мало точек"

    # Count original data points within the interval
    in_interval = (selection["temp"] >= left) & (selection["temp"] <= right)
    if in_interval.sum() < 2:
        return "Тепловой эффект: слишком мало точек"

    # Step 3: Interpolate DTA at exact boundaries
    temp = selection["temp"].to_numpy(dtype=float)
    dta = selection["deltatemp"].to_numpy(dtype=float)

    # Check if boundaries are within data range
    data_tmin = temp.min()
    data_tmax = temp.max()

    if left < data_tmin or right > data_tmax:
        return f"Тепловой эффект: интервал [{left:.1f}, {right:.1f}] выходит за пределы данных [{data_tmin:.1f}, {data_tmax:.1f}]"

    # Interpolate DTA at boundaries
    dta_left = np.interp(left, temp, dta)
    dta_right = np.interp(right, temp, dta)

    # Step 4: Add boundary points to the interval
    # Create extended selection with boundary points
    extended_temp = np.concatenate([[left], temp, [right]])
    extended_dta = np.concatenate([[dta_left], dta, [dta_right]])

    # Filter to interval (inclusive)
    mask = (extended_temp >= left) & (extended_temp <= right)
    filtered_temp = extended_temp[mask]
    filtered_dta = extended_dta[mask]

    # Sort and deduplicate
    sort_idx = np.argsort(filtered_temp)
    filtered_temp = filtered_temp[sort_idx]
    filtered_dta = filtered_dta[sort_idx]

    # Remove duplicates (keep first)
    unique_mask = np.concatenate([[True], np.diff(filtered_temp) > 1e-10])
    filtered_temp = filtered_temp[unique_mask]
    filtered_dta = filtered_dta[unique_mask]

    if len(filtered_temp) < 2:
        return "Тепловой эффект: слишком мало точек"

    # Step 5: Build linear baseline between boundary values
    # baseline(T) = dta_left + (dta_right - dta_left) * (T - left) / (right - left)
    t_range = right - left
    baseline = dta_left + (dta_right - dta_left) * (filtered_temp - left) / t_range

    # Step 6: Integrate DTA(T) - baseline(T) dT
    corrected_dta = filtered_dta - baseline
    integral_value = np.trapezoid(corrected_dta, filtered_temp)

    # Step 7: Apply calibration coefficient
    # Note: EFFECT_SCALE_K is a calibration factor, not a physical constant.
    # The result should be treated as "calibrated thermal effect" not "true thermal effect".
    scaled_effect = EFFECT_SCALE_K * integral_value

    # Step 8: Divide by initial mass
    mass = float(init_mass)
    if mass == 0:
        return "Тепловой эффект: начальная масса должна быть ненулевой"

    result = scaled_effect / mass

    # Format result
    if abs(result) < 1e-6:
        return f"Тепловой эффект: {result:.6g} Дж/г (в пределах шума)"

    return f"Тепловой эффект: {result:.6g} Дж/г"