from __future__ import annotations

import numpy as np

from tgapp.domain.models import (
    InsufficientDataError,
    NonMonotonicAxisError,
    ThermogramValidationError,
    ValidatedThermogram,
)


def validate_parsed(
    temp: np.ndarray,
    deltatemp: np.ndarray | None,
    time: np.ndarray,
    mass: np.ndarray,
    min_points: int = 3,
) -> ValidatedThermogram:
    """Валидировать парсированную термограмму."""
    # 1. Проверить одинаковую длину
    lengths = {len(temp), len(time), len(mass)}
    if deltatemp is not None:
        lengths.add(len(deltatemp))
    if len(lengths) != 1:
        raise ThermogramValidationError(
            f"Массивы разной длины: temp={len(temp)}, time={len(time)}, mass={len(mass)}"
        )

    n = len(temp)
    if n < min_points:
        raise InsufficientDataError(f"Слишком мало точек: {n} < {min_points}")

    # 2. Проверить на inf/-inf
    if np.any(~np.isfinite(temp)):
        raise ThermogramValidationError("Температура содержит inf/-inf")
    if np.any(~np.isfinite(mass)):
        raise ThermogramValidationError("Масса содержит inf/-inf")
    if deltatemp is not None and np.any(~np.isfinite(deltatemp)):
        raise ThermogramValidationError("DTA содержит inf/-inf")

    # 3. Проверить монотонность времени
    time_diffs = np.diff(time)
    if np.any(time_diffs < -1e-10):
        raise NonMonotonicAxisError("Время не монотонно (обратное движение)")

    # 4. Проверить монотонность температуры (возрастающая или убывающая)
    # Allow small fluctuations typical of TGA instruments (up to 0.5°C reversal)
    temp_diffs = np.diff(temp)
    if np.any(temp_diffs < -0.5):
        raise NonMonotonicAxisError("Температура не монотонна (обратное движение)")

    # 5. Удалить NaN строки (но НЕ интерполировать начальные/конечные)
    valid_mask = np.ones(n, dtype=bool)
    valid_mask &= np.isfinite(temp)
    valid_mask &= np.isfinite(time)
    valid_mask &= np.isfinite(mass)
    if deltatemp is not None:
        valid_mask &= np.isfinite(deltatemp)

    n_removed = n - int(valid_mask.sum())

    # Найти первые и последние валидные индексы
    valid_indices = np.where(valid_mask)[0]
    if len(valid_indices) == 0:
        raise InsufficientDataError("Все строки содержат NaN в temp/time/mass")

    first_valid = valid_indices[0]
    last_valid = valid_indices[-1]

    # Начальные и конечные NaN НЕ интерполируются — удаляются
    # Внутренние NaN интерполируются
    filtered_temp = temp[first_valid:last_valid + 1]
    filtered_time = time[first_valid:last_valid + 1]
    filtered_mass = mass[first_valid:last_valid + 1]

    filtered_deltatemp = None
    n_nan = 0
    if deltatemp is not None:
        filtered_deltatemp = deltatemp[first_valid:last_valid + 1].copy()
        nan_mask = ~np.isfinite(filtered_deltatemp)
        n_nan = int(nan_mask.sum())
        if n_nan > 0:
            # Интерполировать внутренние NaN
            valid_dta = np.where(nan_mask)[0]
            if len(valid_dta) > 0:
                filtered_deltatemp = np.interp(
                    valid_dta,
                    np.where(~nan_mask)[0],
                    filtered_deltatemp[~nan_mask],
                )

    # Проверить что осталось достаточно точек
    if len(filtered_temp) < min_points:
        raise InsufficientDataError(
            f"После очистки осталось {len(filtered_temp)} точек < {min_points}"
        )

    return ValidatedThermogram(
        name="",
        temp=filtered_temp,
        deltatemp=filtered_deltatemp,
        time=filtered_time,
        mass=filtered_mass,
        metadata={
            "rows_removed": n_removed,
            "rows_interpolated": n_nan,
            "monotonic_temp": bool(np.all(np.diff(filtered_temp) >= -1e-10)),
            "monotonic_time": bool(np.all(np.diff(filtered_time) >= -1e-10)),
        },
    )