"""Use case: create a new kinetic study."""

from __future__ import annotations

import uuid

from tgapp.domain.kinetics.errors import KineticValidationError
from tgapp.domain.kinetics.models import (
    KineticStudy,
    ConversionSettings,
    HeatingValidationSettings,
    KineticQualitySettings,
)


def create_kinetic_study(
    name: str,
    sample_name: str | None = None,
    atmosphere: str | None = None,
) -> KineticStudy:
    """Create a new empty kinetic study.

    Args:
        name: study display name
        sample_name: optional sample identifier
        atmosphere: optional atmosphere description

    Returns:
        New empty KineticStudy
    """
    study_id = str(uuid.uuid4())

    return KineticStudy(
        study_id=study_id,
        name=name,
        runs=(),
        excluded_run_ids=frozenset(),
        conversion_settings=ConversionSettings(),
        validation_settings=HeatingValidationSettings(),
        sample_name=sample_name,
        atmosphere=atmosphere,
    )