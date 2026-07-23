from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Mapping, Any

import numpy as np

from tgapp.domain.kinetics.units import TemperatureUnit, TimeUnit, MassUnit


@dataclass(frozen=True, slots=True)
class KineticRun:
    run_id: str
    source_name: str
    source_sha256: str

    temperature_k: np.ndarray
    time_s: np.ndarray
    mass_g: np.ndarray

    nominal_heating_rate_k_s: float | None
    measured_heating_rate_k_s: float
    heating_linearity_r2: float
    heating_max_residual_k: float

    sample_name: str | None
    atmosphere: str | None

    source_temperature_unit: TemperatureUnit
    source_time_unit: TimeUnit
    source_mass_unit: MassUnit

    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Validate invariants
        assert self.temperature_k.ndim == 1, "temperature_k must be 1D"
        assert self.time_s.ndim == 1, "time_s must be 1D"
        assert self.mass_g.ndim == 1, "mass_g must be 1D"
        assert len(self.temperature_k) == len(self.time_s) == len(self.mass_g), "array lengths must match"
        n = len(self.temperature_k)
        assert n >= 3, f"minimum 3 points required, got {n}"
        assert np.all(np.isfinite(self.temperature_k)), "temperature_k must be finite"
        assert np.all(np.isfinite(self.time_s)), "time_s must be finite"
        assert np.all(np.isfinite(self.mass_g)), "mass_g must be finite"
        assert np.all(np.diff(self.time_s) > 0), "time_s must be strictly increasing"
        assert np.all(self.mass_g > 0), "mass_g must be positive"
        assert self.measured_heating_rate_k_s > 0, "measured_heating_rate_k_s must be positive"
        # Make arrays read-only
        self.temperature_k.setflags(write=False)
        self.time_s.setflags(write=False)
        self.mass_g.setflags(write=False)


@dataclass(frozen=True, slots=True)
class HeatingProgram:
    beta_k_s: float
    intercept_k: float
    r_squared: float
    max_absolute_residual_k: float
    point_count: int


@dataclass(frozen=True, slots=True)
class HeatingValidationSettings:
    minimum_r_squared: float = 0.995
    maximum_relative_beta_difference: float = 0.10
    minimum_distinct_beta_ratio: float = 1.05


@dataclass(frozen=True, slots=True)
class ConversionSettings:
    alpha_min: float = 0.05
    alpha_max: float = 0.95
    alpha_step: float = 0.05

    reaction_temperature_range_k: tuple[float, float] | None = None

    initial_plateau_range_k: tuple[float, float] | None = None
    final_plateau_range_k: tuple[float, float] | None = None

    plateau_statistic: str = "median"
    minimum_plateau_points: int = 5

    monotonicity_tolerance: float = 1e-6


@dataclass(frozen=True, slots=True)
class KineticStudy:
    study_id: str
    name: str

    runs: tuple[KineticRun, ...]
    excluded_run_ids: frozenset[str]

    conversion_settings: ConversionSettings
    validation_settings: HeatingValidationSettings

    sample_name: str | None
    atmosphere: str | None

    @property
    def active_runs(self) -> tuple[KineticRun, ...]:
        return tuple(r for r in self.runs if r.run_id not in self.excluded_run_ids)


@dataclass(frozen=True, slots=True)
class IsoconversionalRun:
    run_id: str
    beta_k_s: float

    alpha: np.ndarray
    temperature_k: np.ndarray
    time_s: np.ndarray

    conversion_rate_s_inv: np.ndarray | None


@dataclass(frozen=True, slots=True)
class IsoconversionalPoint:
    alpha: float

    run_ids: tuple[str, ...]
    temperatures_k: tuple[float, ...]
    heating_rates_k_s: tuple[float, ...]

    conversion_rates_s_inv: tuple[float, ...] | None


@dataclass(frozen=True, slots=True)
class IsoconversionalDataset:
    points: tuple[IsoconversionalPoint, ...]
    source_run_ids: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class LinearRegressionResult:
    slope: float
    intercept: float
    r_squared: float
    slope_standard_error: float
    intercept_standard_error: float
    residuals: tuple[float, ...]
    predicted: tuple[float, ...]
    point_count: int


@dataclass(frozen=True, slots=True)
class KineticPointResult:
    alpha: float
    activation_energy_j_mol: float | None

    slope: float | None
    intercept: float | None
    r_squared: float | None
    slope_standard_error: float | None

    run_ids: tuple[str, ...]
    temperatures_k: tuple[float, ...]
    heating_rates_k_s: tuple[float, ...]

    regression_x: tuple[float, ...]
    regression_y: tuple[float, ...]
    regression_predicted_y: tuple[float, ...]
    residuals: tuple[float, ...]

    status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KineticAnalysisResult:
    analysis_id: str
    study_id: str

    method_id: str
    method_version: str

    points: tuple[KineticPointResult, ...]

    mean_activation_energy_j_mol: float | None
    median_activation_energy_j_mol: float | None

    source_run_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]

    settings: Mapping[str, Any]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class KineticQualitySettings:
    """Quality thresholds for kinetic study validation."""
    minimum_runs: int = 3
    recommended_runs: int = 4

    minimum_regression_r_squared: float = 0.95
    minimum_heating_r_squared: float = 0.995

    minimum_distinct_beta_ratio: float = 1.05
    maximum_e_relative_standard_error: float = 0.20