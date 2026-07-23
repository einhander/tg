from __future__ import annotations

import numpy as np

from tgapp.domain.kinetics.errors import HeatingProgramError
from tgapp.domain.kinetics.models import HeatingProgram, HeatingValidationSettings


def calculate_heating_program(
    temperature_k: np.ndarray,
    time_s: np.ndarray,
    settings: HeatingValidationSettings | None = None,
) -> HeatingProgram:
    """Calculate numerical heating program via linear regression T(t) = T0 + βt.

    Uses full working range if no reaction range specified.
    """
    if settings is None:
        settings = HeatingValidationSettings()

    n = len(temperature_k)
    if n < 3:
        raise HeatingProgramError(f"Minimum 3 points required, got {n}")

    if not np.all(np.isfinite(temperature_k)) or not np.all(np.isfinite(time_s)):
        raise HeatingProgramError("Temperature or time contains non-finite values")

    if not np.all(np.diff(time_s) > 0):
        raise HeatingProgramError("Time must be strictly increasing")

    temp_range = temperature_k[-1] - temperature_k[0]
    if temp_range <= 0:
        raise HeatingProgramError("Temperature range must be non-zero")

    # Linear regression: T = intercept + beta * t
    coeffs = np.polyfit(time_s, temperature_k, 1)
    beta = coeffs[0]
    intercept = coeffs[1]

    predicted = np.polyval(coeffs, time_s)
    residuals = temperature_k - predicted
    r_squared = 1.0 - (np.sum(residuals ** 2) / (n * np.var(temperature_k, ddof=1)))

    max_residual = float(np.max(np.abs(residuals)))

    if beta <= 0:
        raise HeatingProgramError(f"Heating rate must be positive, got {beta} K/s")

    if r_squared < settings.minimum_r_squared:
        raise HeatingProgramError(
            f"Heating program linearity R²={r_squared:.4f} < "
            f"minimum {settings.minimum_r_squared}"
        )

    return HeatingProgram(
        beta_k_s=float(beta),
        intercept_k=float(intercept),
        r_squared=float(r_squared),
        max_absolute_residual_k=max_residual,
        point_count=n,
    )