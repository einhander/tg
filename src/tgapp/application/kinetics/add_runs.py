"""Use case: add runs to a kinetic study."""

from __future__ import annotations

from tgapp.domain.kinetics.errors import KineticValidationError
from tgapp.domain.kinetics.models import KineticStudy, KineticRun
from tgapp.domain.kinetics.units import TemperatureUnit, TimeUnit, MassUnit


def add_runs_to_kinetic_study(
    study: KineticStudy,
    runs: list[KineticRun],
) -> KineticStudy:
    """Add validated KineticRun objects to a study.

    Args:
        study: the study to add runs to
        runs: list of KineticRun objects (already validated at domain level)

    Returns:
        New KineticStudy with added runs

    Raises:
        KineticValidationError: if runs contain duplicate IDs or invalid data
    """
    existing_ids = {r.run_id for r in study.runs}
    new_ids = {r.run_id for r in runs}

    duplicates = existing_ids & new_ids
    if duplicates:
        raise KineticValidationError(
            f"Duplicate run IDs: {', '.join(sorted(duplicates))}"
        )

    # Remove excluded runs from existing, then add new ones
    excluded = study.excluded_run_ids
    all_runs = tuple(r for r in study.runs if r.run_id not in excluded) + tuple(runs)

    return KineticStudy(
        study_id=study.study_id,
        name=study.name,
        runs=all_runs,
        excluded_run_ids=excluded,
        conversion_settings=study.conversion_settings,
        validation_settings=study.validation_settings,
        sample_name=study.sample_name,
        atmosphere=study.atmosphere,
    )