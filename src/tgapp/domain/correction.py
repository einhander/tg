"""Temperature correction interpolation and validation."""

from __future__ import annotations

import logging
from typing import cast

import numpy as np
import pandas as pd

from tgapp.domain.models import (
    AlignedThermogram,
    CorrectionFile,
    CorrectionRangeError,
    ThermogramValidationError,
)

logger = logging.getLogger(__name__)


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

    # Проверить что температура коррекции монотонна
    if len(corr_temp) > 1 and not np.all(np.diff(corr_temp) > -1e-10):
        # Попытаться отсортировать
        sort_idx = np.argsort(corr_temp)
        corr_temp = corr_temp[sort_idx]
        corr_deltatemp = corr_deltatemp[sort_idx]

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
    """Применить коррекцию к выровненным термограммам.

    Correction применяется к deltatemp каждой термограммы на общей температурной сетке.
    """
    if not aligned:
        return []

    temperature_grid = aligned[0].temperature_grid

    try:
        correction_deltatemp = interpolate_correction_on_grid(correction, temperature_grid)
    except CorrectionRangeError as e:
        logger.warning("Correction skipped: %s", e)
        return aligned

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