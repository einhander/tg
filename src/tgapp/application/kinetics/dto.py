"""DTOs for kinetics application layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(slots=True)
class CreateStudyRequest:
    study_id: str
    name: str
    sample_name: str | None = None
    atmosphere: str | None = None


@dataclass(slots=True)
class AddRunRequest:
    run_id: str
    source_name: str
    source_sha256: str
    temperature_k: list[float]
    time_s: list[float]
    mass_g: list[float]
    nominal_heating_rate_k_s: float | None = None
    measured_heating_rate_k_s: float = 0.0
    heating_linearity_r2: float = 0.0
    heating_max_residual_k: float = 0.0
    sample_name: str | None = None
    atmosphere: str | None = None
    source_temperature_unit: str = "K"
    source_time_unit: str = "s"
    source_mass_unit: str = "g"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class UpdateStudyRequest:
    sample_name: str | None = None
    atmosphere: str | None = None
    reaction_temperature_range_k: tuple[float, float] | None = None
    initial_plateau_range_k: tuple[float, float] | None = None
    final_plateau_range_k: tuple[float, float] | None = None
    alpha_min: float | None = None
    alpha_max: float | None = None
    alpha_step: float | None = None


@dataclass(slots=True)
class ExcludeRunRequest:
    run_id: str
    reason: str


@dataclass(slots=True)
class AnalyzeRequest:
    method_id: str = "ofw_doyle"
    alpha_min: float = 0.05
    alpha_max: float = 0.95
    alpha_step: float = 0.05
    reaction_temperature_range_k: tuple[float, float] | None = None
    initial_plateau_range_k: tuple[float, float] | None = None
    final_plateau_range_k: tuple[float, float] | None = None


@dataclass(slots=True)
class KineticPointDTO:
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


@dataclass(slots=True)
class KineticAnalysisDTO:
    analysis_id: str
    study_id: str
    method_id: str
    method_version: str
    points: tuple[KineticPointDTO, ...]
    mean_activation_energy_j_mol: float | None
    median_activation_energy_j_mol: float | None
    source_run_ids: tuple[str, ...]
    source_hashes: tuple[str, ...]
    settings: Mapping[str, Any]
    warnings: tuple[str, ...]


@dataclass(slots=True)
class RunDTO:
    run_id: str
    source_name: str
    source_sha256: str
    nominal_heating_rate_k_s: float | None
    measured_heating_rate_k_s: float
    heating_linearity_r2: float
    heating_max_residual_k: float
    sample_name: str | None
    atmosphere: str | None
    temperature_range_k: tuple[float, float]
    mass_range_g: tuple[float, float]
    point_count: int


@dataclass(slots=True)
class StudyDTO:
    study_id: str
    name: str
    sample_name: str | None
    atmosphere: str | None
    runs: tuple[RunDTO, ...]
    excluded_run_ids: tuple[str, ...]
    conversion_settings: Mapping[str, Any]
    validation_settings: Mapping[str, Any]
    analysis_ids: tuple[str, ...] = ()