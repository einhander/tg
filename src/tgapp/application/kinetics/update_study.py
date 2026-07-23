"""Use case: update kinetic study settings."""

from __future__ import annotations

from tgapp.domain.kinetics.models import KineticStudy, ConversionSettings


def update_kinetic_study(
    study: KineticStudy,
    sample_name: str | None = None,
    atmosphere: str | None = None,
    reaction_temperature_range_k: tuple[float, float] | None = None,
    initial_plateau_range_k: tuple[float, float] | None = None,
    final_plateau_range_k: tuple[float, float] | None = None,
    alpha_min: float | None = None,
    alpha_max: float | None = None,
    alpha_step: float | None = None,
) -> KineticStudy:
    """Update study metadata and conversion settings.

    Args:
        study: the study to update
        sample_name: optional new sample name
        atmosphere: optional new atmosphere
        reaction_temperature_range_k: optional reaction temperature range
        initial_plateau_range_k: optional initial plateau range
        final_plateau_range_k: optional final plateau range
        alpha_min: optional new alpha minimum
        alpha_max: optional new alpha maximum
        alpha_step: optional new alpha step

    Returns:
        New KineticStudy with updated settings
    """
    # Update conversion settings
    cs = study.conversion_settings
    new_cs = ConversionSettings(
        alpha_min=alpha_min if alpha_min is not None else cs.alpha_min,
        alpha_max=alpha_max if alpha_max is not None else cs.alpha_max,
        alpha_step=alpha_step if alpha_step is not None else cs.alpha_step,
        reaction_temperature_range_k=(
            reaction_temperature_range_k or cs.reaction_temperature_range_k
        ),
        initial_plateau_range_k=(
            initial_plateau_range_k or cs.initial_plateau_range_k
        ),
        final_plateau_range_k=final_plateau_range_k or cs.final_plateau_range_k,
        plateau_statistic=cs.plateau_statistic,
        minimum_plateau_points=cs.minimum_plateau_points,
        monotonicity_tolerance=cs.monotonicity_tolerance,
    )

    return KineticStudy(
        study_id=study.study_id,
        name=study.name,
        runs=study.runs,
        excluded_run_ids=study.excluded_run_ids,
        conversion_settings=new_cs,
        validation_settings=study.validation_settings,
        sample_name=sample_name if sample_name is not None else study.sample_name,
        atmosphere=atmosphere if atmosphere is not None else study.atmosphere,
    )