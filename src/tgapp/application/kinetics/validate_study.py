"""Use case: validate a kinetic study before analysis."""

from __future__ import annotations

from tgapp.domain.kinetics.diagnostics import diagnose_study
from tgapp.domain.kinetics.models import KineticStudy


def validate_kinetic_study(
    study: KineticStudy,
) -> dict:
    """Validate a kinetic study without running OFW.

    Returns a diagnostic report as a dict.
    """
    report = diagnose_study(study)

    return {
        "is_valid": report.is_valid,
        "study_issues": report.study_issues,
        "study_warnings": report.study_warnings,
        "run_diagnostics": [
            {
                "run_id": rd.run_id,
                "source_name": rd.source_name,
                "issues": rd.issues,
                "warnings": rd.warnings,
                "is_valid": rd.is_valid,
            }
            for rd in report.run_diagnostics
        ],
    }