from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Processing settings validation constants
# ---------------------------------------------------------------------------

MIN_BINS = 50
MAX_BINS = 100_000
MAX_SG_WINDOW = 10_001
MIN_SG_POLYORDER = 1
MIN_PEAK_PROMINENCE_SIGMA = 0.01
MIN_SPAN = 0.0
MAX_SPAN = 100.0


def validate_processing_settings(settings: ProcessingSettings) -> list[str]:
    """Validate processing settings. Returns list of error messages.

    Raises InvalidProcessingSettingsError on first invalid field.
    """
    errors = []

    if settings.bins < MIN_BINS:
        errors.append(f"bins ({settings.bins}) < {MIN_BINS}")
    if settings.bins > MAX_BINS:
        errors.append(f"bins ({settings.bins}) > {MAX_BINS}")

    if settings.init_mass <= 0:
        errors.append(f"init_mass ({settings.init_mass}) must be > 0")

    if settings.sg_mode:
        if settings.sg_window % 2 == 0:
            errors.append(f"sg_window ({settings.sg_window}) must be odd")
        if settings.sg_window < 3:
            errors.append(f"sg_window ({settings.sg_window}) < 3")
        if settings.sg_window > MAX_SG_WINDOW:
            errors.append(f"sg_window ({settings.sg_window}) > {MAX_SG_WINDOW}")
        if settings.sg_polyorder < MIN_SG_POLYORDER:
            errors.append(f"sg_polyorder ({settings.sg_polyorder}) < {MIN_SG_POLYORDER}")
        if settings.sg_window <= settings.sg_polyorder:
            errors.append(f"sg_window ({settings.sg_window}) must be > sg_polyorder ({settings.sg_polyorder})")

    if settings.peak_prominence_sigma <= 0:
        errors.append(f"peak_prominence_sigma ({settings.peak_prominence_sigma}) must be > 0")

    if settings.span < MIN_SPAN or settings.span > MAX_SPAN:
        errors.append(f"span ({settings.span}) must be in [{MIN_SPAN}, {MAX_SPAN}]")

    if errors:
        raise InvalidProcessingSettingsError(
            message="; ".join(errors),
            details={"errors": errors},
        )

    return []


@dataclass(slots=True)
class ThermogramFile:
    name: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_kind: str = "upload"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CorrectionFile:
    name: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessingSettings:
    init_mass: float = 1.0
    bins: int = 1000
    mass_smoothing: int = 1
    # DEPRECATED: temp_smoothing is no longer used. Physical axes are never smoothed.
    # NOTE: asdict() includes this field in serialization — low risk, accepted for backward compat.
    temp_smoothing: int = 1
    difflag: int = 1
    use_correction: bool = False
    smooth_dmdt: bool = False
    span: float = 91
    peak_prominence_sigma: float = 5.0
    sg_mode: bool = True
    sg_window: int = 11
    sg_polyorder: int = 3
    hide_tg: bool = False
    hide_dta: bool = False
    hide_dtg: bool = False
    hide_inflections_tg: bool = False
    hide_peaks_dta: bool = False
    hide_peaks_dmdt: bool = False


@dataclass(slots=True)
class ThermogramViewSettings:
    sg_mode: bool = True
    sg_mass_window: int = 11
    sg_temp_window: int = 11
    sg_dtg_window: int = 11
    hide_tg: bool = False
    hide_dta: bool = False
    hide_dtg: bool = False
    hide_peaks_dta: bool = False
    hide_peaks_dmdt: bool = False
    hide_inflections_tg: bool = False
    peak_prominence_sigma: float = 5.0


@dataclass(slots=True)
class PeakResult:
    x: float
    y: float
    label: str = "peak"
    kind: str = "dtg"
    extremum: str = "peak"


@dataclass(slots=True)
class SummaryResult:
    lines: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ThermogramProcessed:
    combined: pd.DataFrame = field(default_factory=pd.DataFrame)
    mass_smoothed: pd.DataFrame = field(default_factory=pd.DataFrame)
    temp_smoothed: pd.DataFrame = field(default_factory=pd.DataFrame)
    derivatives: pd.DataFrame = field(default_factory=pd.DataFrame)
    mean_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    peaks: tuple[PeakResult, ...] = field(default_factory=tuple)
    summary: SummaryResult = field(default_factory=SummaryResult)
    heat_speed_text: str = "Heat speed unavailable"
    adjusted_difflag: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Upload validation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class UploadedThermogramResult:
    """Per-file upload validation result."""

    original_name: str
    accepted: bool
    stored_name: str | None
    parsed_rows: int
    validated_rows: int
    rows_removed: int
    rows_interpolated: int
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Thermogram pipeline models (Phase 4: strict model)
# ---------------------------------------------------------------------------


class ThermogramValidationError(Exception):
    """Базовое исключение валидации термограммы."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message)
        self.details = details or {}


class NonMonotonicAxisError(ThermogramValidationError):
    """Температура или время не монотонны."""


class InsufficientDataError(ThermogramValidationError):
    """Слишком мало точек после очистки."""


class NoCommonRangeError(ThermogramValidationError):
    """Нет общего температурного диапазона между термограммами."""


class CorrectionRangeError(ThermogramValidationError):
    """Корректирующая кривая не покрывает рабочий диапазон."""


class InvalidProcessingSettingsError(ThermogramValidationError):
    """Некорректные параметры обработки."""


class DerivativeCalculationError(ThermogramValidationError):
    """Ошибка расчёта производной."""


@dataclass(slots=True, frozen=True)
class ParsedThermogram:
    """Парсированная термограмма — сырые данные после парсинга."""

    name: str
    temp: np.ndarray
    deltatemp: np.ndarray | None
    time: np.ndarray
    mass: np.ndarray
    metadata: dict = field(default_factory=dict)
    # metadata: original_filename, content_type, rows_parsed, rows_with_nan


@dataclass(slots=True, frozen=True)
class ValidatedThermogram:
    """Валидированная термограмма — проверенные данные."""

    name: str
    temp: np.ndarray
    deltatemp: np.ndarray | None
    time: np.ndarray
    mass: np.ndarray
    metadata: dict = field(default_factory=dict)
    # metadata: rows_removed, rows_interpolated, monotonic_temp, monotonic_time


@dataclass(slots=True, frozen=True)
class AlignedThermogram:
    """Выровненная термограмма — интерполирована на общую температурную сетку."""

    name: str
    temp: np.ndarray  # общая сетка
    deltatemp: np.ndarray | None
    time: np.ndarray
    mass: np.ndarray
    temperature_grid: np.ndarray  # общая ось
    metadata: dict = field(default_factory=dict)
