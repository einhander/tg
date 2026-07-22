"""Temperature correction interpolation and validation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tgapp.domain.models import (
    AlignedThermogram,
    CorrectionFile,
    CorrectionRangeError,
    ThermogramValidationError,
)


def interpolate_correction_on_grid(
    correction: CorrectionFile,
    temperature_grid: np.ndarray,
) -> np.ndarray:
    """Интерполировать correction.deltatemp на общую температурную сетку.

    Args:
        correction: валидированный correction-файл с колонками 'temp' и 'deltatemp'
        temperature_grid: общая температурная сетка термограмм

    Returns:
        Массив скорректированных deltatemp значений

    Raises:
        CorrectionRangeError: если correction не покрывает temperature_grid
        ThermogramValidationError: если correction температура не монотонна после дедупа
    """
    if correction.frame.empty:
        raise CorrectionRangeError("Correction file is empty")

    frame = correction.frame.copy()
    frame["temp"] = pd.to_numeric(frame["temp"], errors="coerce")
    frame["deltatemp"] = pd.to_numeric(frame["deltatemp"], errors="coerce")

    # Удалить строки с NaN в temp или deltatemp
    valid = frame.dropna(subset=["temp", "deltatemp"])
    if len(valid) < 2:
        raise CorrectionRangeError(
            f"Correction has insufficient valid points: {len(valid)} < 2"
        )

    corr_temp = valid["temp"].to_numpy(dtype=float)
    corr_deltatemp = valid["deltatemp"].to_numpy(dtype=float)

    # Handle duplicate temperatures — keep first occurrence (deterministic)
    unique_temp, unique_indices = np.unique(corr_temp, return_index=True)
    if len(unique_indices) < len(corr_temp):
        # Duplicates found — keep first occurrence of each temperature
        corr_temp = unique_temp
        corr_deltatemp = corr_deltatemp[unique_indices]
        # Record in metadata (caller handles this)

    # Проверить что температура коррекции монотонна — не сортируем молча
    if len(corr_temp) > 1 and not np.all(np.diff(corr_temp) > -1e-10):
        raise ThermogramValidationError(
            f"Correction-файл содержит немонотонную температурную ось. "
            f"Обнаружены обратные движения температуры."
        )

    # Check that temperature is strictly increasing after dedup
    if len(corr_temp) > 1 and not np.all(np.diff(corr_temp) > 0):
        raise ThermogramValidationError(
            "Correction temperature is not strictly increasing after deduplication"
        )

    # Проверить покрытие диапазона
    corr_tmin = corr_temp.min()
    corr_tmax = corr_temp.max()
    grid_tmin = temperature_grid.min()
    grid_tmax = temperature_grid.max()

    # Correction должен покрывать весь temperature_grid
    if corr_tmin > grid_tmin + 1e-6 or corr_tmax < grid_tmax - 1e-6:
        raise CorrectionRangeError(
            f"Correction range [{corr_tmin:.1f}, {corr_tmax:.1f}] "
            f"does not cover thermogram range [{grid_tmin:.1f}, {grid_tmax:.1f}]"
        )

    # Интерполировать — np.interp автоматически обрезает за границы,
    # но мы уже проверили покрытие, так что экстраполяции не будет
    corrected = np.interp(temperature_grid, corr_temp, corr_deltatemp)

    return corrected


def apply_correction_to_aligned(
    aligned: list[AlignedThermogram],
    correction: CorrectionFile,
) -> list[AlignedThermogram]:
    """Apply correction to aligned thermograms.

    Raises CorrectionRangeError if correction cannot be applied.
    Does NOT silently skip on errors.
    """
    if not aligned:
        return []

    temperature_grid = aligned[0].temperature_grid

    # Let interpolate_correction_on_grid raise CorrectionRangeError
    correction_deltatemp = interpolate_correction_on_grid(correction, temperature_grid)

    corrected = []
    for a in aligned:
        new_deltatemp = a.deltatemp + correction_deltatemp if a.deltatemp is not None else correction_deltatemp
        corrected.append(AlignedThermogram(
            name=a.name,
            temp=a.temp.copy(),
            deltatemp=new_deltatemp,
            time=a.time.copy(),
            mass=a.mass.copy(),
            temperature_grid=a.temperature_grid.copy(),
            metadata={**a.metadata, "correction_applied": True},
        ))

    return corrected