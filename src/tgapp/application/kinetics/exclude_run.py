"""Use case: exclude a run from a kinetic study."""

from __future__ import annotations

from tgapp.domain.kinetics.models import KineticStudy


def exclude_run_from_study(
    study: KineticStudy,
    run_id: str,
) -> KineticStudy:
    """Exclude a run from the study.

    Args:
        study: the study to modify
        run_id: ID of the run to exclude

    Returns:
        New KineticStudy with run excluded

    Raises:
        ValueError: if run_id not found in study
    """
    run_ids = {r.run_id for r in study.runs}
    if run_id not in run_ids:
        raise ValueError(f"Run {run_id} not found in study")

    new_excluded = study.excluded_run_ids | frozenset({run_id})

    return KineticStudy(
        study_id=study.study_id,
        name=study.name,
        runs=study.runs,
        excluded_run_ids=new_excluded,
        conversion_settings=study.conversion_settings,
        validation_settings=study.validation_settings,
        sample_name=study.sample_name,
        atmosphere=study.atmosphere,
    )