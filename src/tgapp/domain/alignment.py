from __future__ import annotations

import numpy as np

from tgapp.domain.models import (
    AlignedThermogram,
    NoCommonRangeError,
    ThermogramValidationError,
    ValidatedThermogram,
)


def align_thermograms(
    validated: list[ValidatedThermogram],
    bins: int = 500,
) -> list[AlignedThermogram]:
    """Выровнять термограммы на общую температурную сетку."""
    if not validated:
        return []

    # Найти общий диапазон
    tmin_values = [v.temp.min() for v in validated]
    tmax_values = [v.temp.max() for v in validated]

    tmin_common = max(tmin_values)
    tmax_common = min(tmax_values)

    if tmin_common >= tmax_common:
        raise NoCommonRangeError(
            f"Нет общего температурного диапазона: "
            f"Tmin_common={tmin_common:.2f}, Tmax_common={tmax_common:.2f}"
        )

    # Создать общую температурную сетку
    temperature_grid = np.linspace(tmin_common, tmax_common, bins)

    # Интерполировать каждую термограмму на общую сетку
    aligned = []
    for v in validated:
        aligned_mass = np.interp(temperature_grid, v.temp, v.mass)
        aligned_time = np.interp(temperature_grid, v.temp, v.time)

        aligned_deltatemp = None
        if v.deltatemp is not None:
            aligned_deltatemp = np.interp(temperature_grid, v.temp, v.deltatemp)

        aligned.append(AlignedThermogram(
            name=v.name,
            temp=temperature_grid.copy(),
            deltatemp=aligned_deltatemp,
            time=aligned_time,
            mass=aligned_mass,
            temperature_grid=temperature_grid.copy(),
            metadata=v.metadata.copy(),
        ))

    return aligned