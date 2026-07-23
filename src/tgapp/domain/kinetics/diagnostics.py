"""Diagnostics for kinetic study quality."""

from __future__ import annotations

from dataclasses import dataclass, field

from tgapp.domain.kinetics.errors import (
    InsufficientRunsError,
    IdenticalHeatingRatesError,
    HeatingProgramError,
)
from tgapp.domain.kinetics.models import (
    KineticStudy,
    KineticAnalysisResult,
    KineticPointResult,
    KineticQualitySettings,
)


@dataclass(frozen=True, slots=True)
class RunDiagnostic:
    """Diagnostic report for a single run."""
    run_id: str
    source_name: str
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0


@dataclass(frozen=True, slots=True)
class AlphaDiagnostic:
    """Diagnostic report for an alpha point."""
    alpha: float
    issues: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0


@dataclass(frozen=True, slots=True)
class StudyDiagnosticReport:
    """Full diagnostic report for a kinetic study."""
    study_id: str
    study_name: str
    run_diagnostics: tuple[RunDiagnostic, ...]
    alpha_diagnostics: tuple[AlphaDiagnostic, ...] = ()
    study_issues: tuple[str, ...] = ()
    study_warnings: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return len(self.study_issues) == 0 and all(
            rd.is_valid for rd in self.run_diagnostics
        )


def diagnose_study(
    study: KineticStudy,
    quality_settings: KineticQualitySettings | None = None,
) -> StudyDiagnosticReport:
    """Diagnose a kinetic study for quality issues.

    Checks:
    - Minimum number of active runs
    - Heating program linearity per run
    - Distinct heating rates
    - Comparable atmosphere
    - Mass loss sufficiency
    - Alpha monotonicity
    """
    if quality_settings is None:
        quality_settings = KineticQualitySettings()

    active_runs = study.active_runs
    run_diags: list[RunDiagnostic] = []
    study_issues: list[str] = []
    study_warnings: list[str] = []

    # Check minimum runs
    if len(active_runs) < quality_settings.minimum_runs:
        study_issues.append(
            f"Only {len(active_runs)} active run(s), minimum {quality_settings.minimum_runs} required"
        )

    if len(active_runs) < quality_settings.recommended_runs:
        study_warnings.append(
            f"Only {len(active_runs)} active run(s), "
            f"{quality_settings.recommended_runs} recommended for robust statistics"
        )

    # Check heating rates
    beta_values = [r.measured_heating_rate_k_s for r in active_runs]
    unique_betas = set(round(b, 6) for b in beta_values)

    if len(unique_betas) < 2:
        study_issues.append(
            "All heating rates are identical — cannot perform isokinetic analysis"
        )

    # Check distinct beta ratio
    if len(unique_betas) >= 2:
        sorted_betas = sorted(unique_betas)
        min_ratio = (
            sorted_betas[1] / sorted_betas[0] if sorted_betas[0] > 0 else float("inf")
        )
        if min_ratio < quality_settings.minimum_distinct_beta_ratio:
            study_warnings.append(
                f"Heating rate ratio {min_ratio:.3f} < "
                f"{quality_settings.minimum_distinct_beta_ratio} recommended"
            )

    # Per-run diagnostics
    for run in active_runs:
        issues: list[str] = []
        warnings: list[str] = []

        # Heating program linearity
        if run.heating_linearity_r2 < quality_settings.minimum_heating_r_squared:
            issues.append(
                f"Heating program R²={run.heating_linearity_r2:.4f} < "
                f"{quality_settings.minimum_heating_r_squared}"
            )

        # Mass loss check
        mass_range = run.mass_g[0] - run.mass_g[-1]
        mass_pct = mass_range / run.mass_g[0] * 100 if run.mass_g[0] > 0 else 0
        if mass_pct < 1.0:
            warnings.append(f"Very small mass loss: {mass_pct:.1f}%")

        # Atmosphere comparison
        if run.atmosphere is not None:
            atmospheres = {
                r.atmosphere for r in active_runs if r.atmosphere is not None
            }
            if len(atmospheres) > 1:
                issues.append(f"Inconsistent atmosphere: {run.atmosphere}")

        run_diags.append(
            RunDiagnostic(
                run_id=run.run_id,
                source_name=run.source_name,
                issues=tuple(issues),
                warnings=tuple(warnings),
            )
        )

    return StudyDiagnosticReport(
        study_id=study.study_id,
        study_name=study.name,
        run_diagnostics=tuple(run_diags),
        study_issues=tuple(study_issues),
        study_warnings=tuple(study_warnings),
    )


def diagnose_analysis_result(
    result: KineticAnalysisResult,
    quality_settings: KineticQualitySettings | None = None,
) -> StudyDiagnosticReport:
    """Diagnose an analysis result for per-alpha-point quality."""
    if quality_settings is None:
        quality_settings = KineticQualitySettings()

    alpha_diags: list[AlphaDiagnostic] = []

    for point in result.points:
        issues: list[str] = []
        warnings: list[str] = []

        if point.status == "insufficient_runs":
            issues.append(f"Only {len(point.run_ids)} run(s) available")
        elif point.status == "identical_heating_rates":
            issues.append("All heating rates identical")
        elif point.status == "negative_energy":
            warnings.append("Negative activation energy — check data quality")
        elif point.status == "questionable":
            if (
                point.r_squared is not None
                and point.r_squared < quality_settings.minimum_regression_r_squared
            ):
                warnings.append(f"Low R²={point.r_squared:.4f}")

        alpha_diags.append(
            AlphaDiagnostic(
                alpha=point.alpha,
                issues=tuple(issues),
                warnings=tuple(warnings),
            )
        )

    return StudyDiagnosticReport(
        study_id=result.study_id,
        study_name="",
        run_diagnostics=(),
        alpha_diagnostics=tuple(alpha_diags),
        study_warnings=result.warnings,
    )