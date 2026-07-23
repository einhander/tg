"""API routes for kinetic analysis (OFW Doyle)."""

from __future__ import annotations

import numpy as np

from fastapi import APIRouter, HTTPException, Request, Response

from tgapp.application.kinetics.analyze_study import analyze_kinetic_study
from tgapp.application.kinetics.create_study import create_kinetic_study
from tgapp.application.kinetics.dto import (
    AddRunRequest,
    AnalyzeRequest,
    CreateStudyRequest,
    ExcludeRunRequest,
    UpdateStudyRequest,
)
from tgapp.application.kinetics.exclude_run import exclude_run_from_study
from tgapp.application.kinetics.update_study import update_kinetic_study
from tgapp.application.kinetics.validate_study import validate_kinetic_study
from tgapp.application.kinetics.add_runs import add_runs_to_kinetic_study
from tgapp.domain.kinetics.errors import KineticValidationError
from tgapp.domain.kinetics.models import KineticRun
from tgapp.domain.kinetics.units import TemperatureUnit, TimeUnit, MassUnit
from tgapp.infrastructure.kinetics.repository import KineticStudyRepository
from tgapp.web.deps import get_kinetics_repo, get_or_create_session_state

router = APIRouter(prefix="/api/kinetics")


@router.post("/studies", status_code=201)
def create_study_endpoint(
    request: Request,
    response: Response,
    body: CreateStudyRequest,
):
    """Create a new kinetic study."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    try:
        study = create_kinetic_study(
            name=body.name,
            sample_name=body.sample_name,
            atmosphere=body.atmosphere,
        )
    except KineticValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo.save_study(study)

    return {
        "study_id": study.study_id,
        "name": study.name,
        "sample_name": study.sample_name,
        "atmosphere": study.atmosphere,
        "run_count": len(study.runs),
        "excluded_run_ids": list(study.excluded_run_ids),
    }


@router.post("/studies/{study_id}/runs", status_code=201)
def add_run_endpoint(
    request: Request,
    response: Response,
    study_id: str,
    body: AddRunRequest,
):
    """Add a run to an existing kinetic study."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    try:
        study = repo.load_study_full(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    run = KineticRun(
        run_id=body.run_id,
        source_name=body.source_name,
        source_sha256=body.source_sha256,
        temperature_k=np.array(body.temperature_k, dtype=np.float64),
        time_s=np.array(body.time_s, dtype=np.float64),
        mass_g=np.array(body.mass_g, dtype=np.float64),
        nominal_heating_rate_k_s=body.nominal_heating_rate_k_s,
        measured_heating_rate_k_s=body.measured_heating_rate_k_s,
        heating_linearity_r2=body.heating_linearity_r2,
        heating_max_residual_k=body.heating_max_residual_k,
        sample_name=body.sample_name,
        atmosphere=body.atmosphere,
        source_temperature_unit=TemperatureUnit(body.source_temperature_unit),
        source_time_unit=TimeUnit(body.source_time_unit),
        source_mass_unit=MassUnit(body.source_mass_unit),
        metadata=body.metadata,
    )

    try:
        updated = add_runs_to_kinetic_study(study, [run])
    except KineticValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo.save_study(updated)

    return {
        "study_id": updated.study_id,
        "run_count": len(updated.runs),
        "run_id": body.run_id,
    }


@router.patch("/studies/{study_id}")
def update_study_endpoint(
    request: Request,
    response: Response,
    study_id: str,
    body: UpdateStudyRequest,
):
    """Update study metadata and conversion settings."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    try:
        study = repo.load_study_full(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    try:
        updated = update_kinetic_study(
            study=study,
            sample_name=body.sample_name,
            atmosphere=body.atmosphere,
            reaction_temperature_range_k=body.reaction_temperature_range_k,
            initial_plateau_range_k=body.initial_plateau_range_k,
            final_plateau_range_k=body.final_plateau_range_k,
            alpha_min=body.alpha_min,
            alpha_max=body.alpha_max,
            alpha_step=body.alpha_step,
        )
    except KineticValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo.save_study(updated)

    return {
        "study_id": updated.study_id,
        "name": updated.name,
        "sample_name": updated.sample_name,
        "atmosphere": updated.atmosphere,
    }


@router.post("/studies/{study_id}/exclude")
def exclude_run_endpoint(
    request: Request,
    response: Response,
    study_id: str,
    body: ExcludeRunRequest,
):
    """Exclude a run from a kinetic study."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    try:
        study = repo.load_study_full(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    try:
        updated = exclude_run_from_study(study, body.run_id)
    except KineticValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo.save_study(updated)

    return {
        "study_id": updated.study_id,
        "excluded_run_id": body.run_id,
        "excluded_run_ids": list(updated.excluded_run_ids),
    }


@router.get("/studies/{study_id}")
def get_study_endpoint(
    request: Request,
    response: Response,
    study_id: str,
):
    """Get study details including runs and analysis IDs."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    try:
        study = repo.load_study_full(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    runs = []
    for r in study.runs:
        runs.append({
            "run_id": r.run_id,
            "source_name": r.source_name,
            "source_sha256": r.source_sha256,
            "nominal_heating_rate_k_s": r.nominal_heating_rate_k_s,
            "measured_heating_rate_k_s": r.measured_heating_rate_k_s,
            "heating_linearity_r2": r.heating_linearity_r2,
            "heating_max_residual_k": r.heating_max_residual_k,
            "sample_name": r.sample_name,
            "atmosphere": r.atmosphere,
        })

    return {
        "study_id": study.study_id,
        "name": study.name,
        "sample_name": study.sample_name,
        "atmosphere": study.atmosphere,
        "runs": runs,
        "excluded_run_ids": list(study.excluded_run_ids),
        "conversion_settings": {
            "alpha_min": study.conversion_settings.alpha_min,
            "alpha_max": study.conversion_settings.alpha_max,
            "alpha_step": study.conversion_settings.alpha_step,
            "reaction_temperature_range_k": study.conversion_settings.reaction_temperature_range_k,
            "initial_plateau_range_k": study.conversion_settings.initial_plateau_range_k,
            "final_plateau_range_k": study.conversion_settings.final_plateau_range_k,
            "plateau_statistic": study.conversion_settings.plateau_statistic,
            "minimum_plateau_points": study.conversion_settings.minimum_plateau_points,
            "monotonicity_tolerance": study.conversion_settings.monotonicity_tolerance,
        },
        "validation_settings": {
            "minimum_r_squared": study.validation_settings.minimum_r_squared,
            "maximum_relative_beta_difference": study.validation_settings.maximum_relative_beta_difference,
            "minimum_distinct_beta_ratio": study.validation_settings.minimum_distinct_beta_ratio,
        },
        "analysis_ids": repo.list_analyses(study_id),
    }


@router.post("/studies/{study_id}/analyze", status_code=201)
def analyze_endpoint(
    request: Request,
    response: Response,
    study_id: str,
    body: AnalyzeRequest | None = None,
):
    """Run kinetic analysis on a validated study."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    if body is None:
        body = AnalyzeRequest()

    try:
        study = repo.load_study_full(study_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Study {study_id} not found")

    try:
        result, dataset = analyze_kinetic_study(
            study=study,
            method_id=body.method_id,
        )
    except KineticValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))

    repo.save_analysis(result)

    return {
        "analysis_id": result.analysis_id,
        "study_id": result.study_id,
        "method_id": result.method_id,
        "method_version": result.method_version,
        "mean_activation_energy_j_mol": result.mean_activation_energy_j_mol,
        "median_activation_energy_j_mol": result.median_activation_energy_j_mol,
        "point_count": len(result.points),
        "warnings": list(result.warnings),
    }


@router.get("/studies/{study_id}/analyses/{analysis_id}")
def get_analysis_endpoint(
    request: Request,
    response: Response,
    study_id: str,
    analysis_id: str,
):
    """Get analysis result."""
    session_state = get_or_create_session_state(request, response)
    repo = get_kinetics_repo(request)

    try:
        result_data = repo.load_analysis(study_id, analysis_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Analysis {analysis_id} not found")

    return result_data