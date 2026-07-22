from __future__ import annotations

import numpy as np

from tgapp.domain.models import (
    InsufficientDataError,
    NonMonotonicAxisError,
    ThermogramValidationError,
    ValidatedThermogram,
)

TIME_EPSILON = 1e-9
TEMP_EPSILON = 1e-3
MIN_POINTS = 3
MAX_INTERPOLATION_GAP_POINTS = 100
MAX_INTERPOLATED_FRACTION = 0.1


def validate_parsed(
    temp: np.ndarray,
    deltatemp: np.ndarray | None,
    time: np.ndarray,
    mass: np.ndarray,
    min_points: int = MIN_POINTS,
    max_interpolation_gap_points: int = MAX_INTERPOLATION_GAP_POINTS,
    max_interpolated_fraction: float = MAX_INTERPOLATED_FRACTION,
) -> ValidatedThermogram:
    """Валидировать парсированную термограмму.

    Policy:
    - inf/-inf → always error in all columns
    - NaN in axes (temp/time) → remove row
    - NaN in mass → strip edges, interpolate internal gaps
    - NaN in DTA → same as mass
    - Strictly increasing time (with TIME_EPSILON)
    """
    n = len(temp)

    # 1. Check equal lengths
    lengths = {len(temp), len(time), len(mass)}
    if deltatemp is not None:
        lengths.add(len(deltatemp))
    if len(lengths) != 1:
        raise ThermogramValidationError(
            f"Массивы разной длины: temp={len(temp)}, time={len(time)}, mass={len(mass)}"
        )

    # 2. Check minimum length
    if n < min_points:
        raise InsufficientDataError(f"Слишком мало точек: {n} < {min_points}")

    # 3. Separate inf from NaN
    # inf/-inf → always error
    if np.any(~np.isfinite(temp)):
        raise ThermogramValidationError("Температура содержит inf/-inf")
    if np.any(~np.isfinite(time)):
        raise ThermogramValidationError("Время содержит inf/-inf")
    if np.any(~np.isfinite(mass)):
        raise ThermogramValidationError("Масса содержит inf/-inf")
    if deltatemp is not None and np.any(~np.isfinite(deltatemp)):
        raise ThermogramValidationError("DTA содержит inf/-inf")

    # 4. Check strictly increasing time (with epsilon)
    time_diffs = np.diff(time)
    if np.any(time_diffs <= TIME_EPSILON):
        raise NonMonotonicAxisError("Время не строго возрастает (повторяющиеся или убывающие значения)")

    # 5. Check temperature monotonicity (strict with epsilon)
    temp_diffs = np.diff(temp)
    if np.any(temp_diffs < -TEMP_EPSILON):
        raise NonMonotonicAxisError("Температура не монотонна (обратное движение)")

    # 6. Handle NaN in axes (temp/time) — remove rows
    valid_mask = np.ones(n, dtype=bool)
    valid_mask &= np.isfinite(temp)
    valid_mask &= np.isfinite(time)
    n_removed_axis_nan = int((~valid_mask).sum())

    # 7. Handle NaN in signals (mass, deltatemp)
    # Strip edge NaNs, interpolate internal gaps
    mass_nan = ~np.isfinite(mass)
    dta_nan = None
    if deltatemp is not None:
        dta_nan = ~np.isfinite(deltatemp)

    # Find first/last valid indices for mass
    valid_mass_indices = np.where(~mass_nan)[0]
    if len(valid_mass_indices) == 0:
        raise InsufficientDataError("Все значения массы NaN")

    first_valid_mass = valid_mass_indices[0]
    last_valid_mass = valid_mass_indices[-1]

    # Count edge NaNs in mass
    n_edge_mass = first_valid_mass + (n - 1 - last_valid_mass)
    # Count internal NaNs in mass
    internal_mass_mask = mass_nan[first_valid_mass:last_valid_mass + 1]
    n_internal_mass = int(internal_mass_mask.sum())

    # Check internal mass gap length
    if n_internal_mass > 0:
        # Find contiguous NaN segments
        mass_nan_segment = mass_nan[first_valid_mass:last_valid_mass + 1]
        gaps = np.diff(np.where(mass_nan_segment)[0])
        if len(gaps) > 0:
            max_gap = int(gaps.max()) + 1
            if max_gap > max_interpolation_gap_points:
                raise ThermogramValidationError(
                    f"Разрыв в массе слишком длинный: {max_gap} точек > {max_interpolation_gap_points}"
                )

        # Check interpolated fraction
        internal_range = last_valid_mass - first_valid_mass + 1
        interpolated_fraction = n_internal_mass / internal_range
        if interpolated_fraction > max_interpolated_fraction:
            raise ThermogramValidationError(
                f"Доля восстановленных значений массы слишком велика: {interpolated_fraction:.1%} > {max_interpolated_fraction:.0%}"
            )

    # 8. Slice to first/last valid mass indices (removes edge NaNs)
    filtered_temp = temp[first_valid_mass:last_valid_mass + 1].copy()
    filtered_time = time[first_valid_mass:last_valid_mass + 1].copy()
    filtered_mass = mass[first_valid_mass:last_valid_mass + 1].copy()

    filtered_deltatemp = None
    n_dta_interpolated = 0
    if deltatemp is not None:
        filtered_deltatemp = deltatemp[first_valid_mass:last_valid_mass + 1].copy()
        dta_nan_internal = ~np.isfinite(filtered_deltatemp)
        n_dta_internal = int(dta_nan_internal.sum())

        if n_dta_internal > 0:
            # Check DTA gap length
            dta_nan_segment = dta_nan_internal
            gaps = np.diff(np.where(dta_nan_segment)[0])
            if len(gaps) > 0:
                max_gap = int(gaps.max()) + 1
                if max_gap > max_interpolation_gap_points:
                    raise ThermogramValidationError(
                        f"Разрыв в DTA слишком длинный: {max_gap} точек > {max_interpolation_gap_points}"
                    )

            # Interpolate DTA NaNs
            valid_dta = np.where(~dta_nan_internal)[0]
            if len(valid_dta) > 0:
                filtered_deltatemp = np.interp(
                    np.where(dta_nan_internal)[0],
                    valid_dta,
                    filtered_deltatemp[~dta_nan_internal],
                )
                n_dta_interpolated = n_dta_internal

        # Also apply axis-valid mask to DTA (rows removed by axis NaN)
        # (axis NaN already handled by slicing to mass range)

    # 9. Re-check after cleaning
    if len(filtered_temp) < min_points:
        raise InsufficientDataError(
            f"После очистки осталось {len(filtered_temp)} точек < {min_points}"
        )

    # 10. Re-check monotonicity after slicing
    if len(filtered_time) > 1 and not np.all(np.diff(filtered_time) > TIME_EPSILON):
        raise NonMonotonicAxisError("Время не строго возрастает после очистки")

    if len(filtered_temp) > 1 and not np.all(np.diff(filtered_temp) >= -TEMP_EPSILON):
        raise NonMonotonicAxisError("Температура не монотонна после очистки")

    # 11. Build metadata
    total_removed = n_removed_axis_nan + n_edge_mass
    metadata = {
        "rows_original": n,
        "rows_removed_axis_nan": n_removed_axis_nan,
        "rows_removed_edge_nan": n_edge_mass,
        "mass_points_interpolated": n_internal_mass,
        "dta_points_interpolated": n_dta_interpolated,
        "interpolated_fraction": (n_internal_mass / (last_valid_mass - first_valid_mass + 1)) if (last_valid_mass - first_valid_mass + 1) > 0 else 0.0,
        "monotonic_temp": bool(np.all(np.diff(filtered_temp) >= -TEMP_EPSILON)),
        "monotonic_time": bool(np.all(np.diff(filtered_time) > TIME_EPSILON)),
    }

    return ValidatedThermogram(
        name="",
        temp=filtered_temp,
        deltatemp=filtered_deltatemp,
        time=filtered_time,
        mass=filtered_mass,
        metadata=metadata,
    )