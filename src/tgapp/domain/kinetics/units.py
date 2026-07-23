from enum import StrEnum
import numpy as np


class TemperatureUnit(StrEnum):
    CELSIUS = "degC"
    KELVIN = "K"


class TimeUnit(StrEnum):
    SECOND = "s"
    MINUTE = "min"


class MassUnit(StrEnum):
    MILLIGRAM = "mg"
    GRAM = "g"
    PERCENT = "%"


def to_kelvin(values: np.ndarray, source_unit: TemperatureUnit) -> np.ndarray:
    """Convert temperature values to Kelvin."""
    arr = np.asarray(values, dtype=np.float64)
    if source_unit == TemperatureUnit.CELSIUS:
        return arr + 273.15
    return arr


def to_seconds(values: np.ndarray, source_unit: TimeUnit) -> np.ndarray:
    """Convert time values to seconds."""
    arr = np.asarray(values, dtype=np.float64)
    if source_unit == TimeUnit.MINUTE:
        return arr * 60.0
    return arr


def to_grams(values: np.ndarray, source_unit: MassUnit) -> np.ndarray:
    """Convert mass values to grams."""
    arr = np.asarray(values, dtype=np.float64)
    if source_unit == MassUnit.MILLIGRAM:
        return arr / 1000.0
    if source_unit == MassUnit.PERCENT:
        # Percent mass — return as-is (already fraction-like)
        return arr
    return arr