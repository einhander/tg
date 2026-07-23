"""Use case: run kinetic analysis on a study."""

from __future__ import annotations

import uuid

from tgapp.domain.kinetics.errors import KineticValidationError
from tgapp.domain.kinetics.methods.ofw import OzawaFlynnWallMethod
from tgapp.domain.kinetics.models import (
    KineticAnalysisResult,
    KineticStudy,
    IsoconversionalRun,
    ConversionSettings,
)
from tgapp.domain.kinetics.interpolation import (
    build_alpha_grid,
    build_isoconversional_dataset,
)
from tgapp.domain.kinetics.conversion import calculate_conversion


def analyze_kinetic_study(
    study: KineticStudy,
    method_id: str = "ofw_doyle",
) -> tuple:
    """Run kinetic analysis on a validated study.

    Pipeline:
    1. Load study
    2. Validate runs
    3. Calculate conversion per run
    4. Build isoconversional dataset
    5. Run OFW
    6. Return result

    Args:
        study: validated KineticStudy
        method_id: method identifier (currently only "ofw_doyle" supported)

    Returns:
        (KineticAnalysisResult, isoconversional_dataset)

    Raises:
        KineticValidationError: if study validation fails
    """
    active_runs = study.active_runs

    if len(active_runs) < 3:
        raise KineticValidationError(
            f"Need at least 3 active runs for analysis, got {len(active_runs)}"
        )

    # Calculate conversion for each run
    conversion_settings = study.conversion_settings
    isoconversional_runs: list[IsoconversionalRun] = []

    for run in active_runs:
        try:
            alpha, temp_k, time_s = calculate_conversion(run, conversion_settings)
        except Exception as e:
            raise KineticValidationError(
                f"Conversion calculation failed for run {run.run_id}: {e}"
            ) from e

        iso_run = IsoconversionalRun(
            run_id=run.run_id,
            beta_k_s=run.measured_heating_rate_k_s,
            alpha=alpha,
            temperature_k=temp_k,
            time_s=time_s,
            conversion_rate_s_inv=None,
        )
        isoconversional_runs.append(iso_run)

    # Build alpha grid and dataset
    alpha_grid = build_alpha_grid(conversion_settings)
    dataset = build_isoconversional_dataset(isoconversional_runs, alpha_grid)

    # Run method
    if method_id == "ofw_doyle":
        method = OzawaFlynnWallMethod()
    else:
        raise KineticValidationError(f"Unknown method: {method_id}")

    result = method.analyze(dataset)

    # Update study_id in result
    result = KineticAnalysisResult(
        analysis_id=result.analysis_id,
        study_id=study.study_id,
        method_id=result.method_id,
        method_version=result.method_version,
        points=result.points,
        mean_activation_energy_j_mol=result.mean_activation_energy_j_mol,
        median_activation_energy_j_mol=result.median_activation_energy_j_mol,
        source_run_ids=result.source_run_ids,
        source_hashes=result.source_hashes,
        settings={
            "alpha_min": conversion_settings.alpha_min,
            "alpha_max": conversion_settings.alpha_max,
            "alpha_step": conversion_settings.alpha_step,
            "initial_plateau_range_k": conversion_settings.initial_plateau_range_k,
            "final_plateau_range_k": conversion_settings.final_plateau_range_k,
        },
        warnings=result.warnings,
    )

    return result, dataset