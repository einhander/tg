from __future__ import annotations

import numpy as np
from scipy import stats

from tgapp.domain.kinetics.errors import RegressionError
from tgapp.domain.kinetics.models import LinearRegressionResult


def linear_regression(
    x: np.ndarray,
    y: np.ndarray,
) -> LinearRegressionResult:
    """Perform linear regression y = slope * x + intercept.

    Requirements:
    - Minimum 3 points
    - All values finite
    - Non-zero variance in x
    - No automatic outlier removal
    - No rounding before regression
    - Deterministic result
    - Preserves original x and y in result

    Args:
        x: independent variable array
        y: dependent variable array

    Returns:
        LinearRegressionResult with slope, intercept, R², standard errors,
        residuals, predicted

    Raises:
        RegressionError: if requirements not met
    """
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)

    n = len(x)
    if n != len(y):
        raise RegressionError(
            f"x and y must have same length: {len(x)} vs {len(y)}"
        )
    if n < 3:
        raise RegressionError(f"Minimum 3 points required, got {n}")
    if not np.all(np.isfinite(x)) or not np.all(np.isfinite(y)):
        raise RegressionError("x and y must contain only finite values")

    x_var = np.var(x, ddof=1)
    if x_var == 0:
        raise RegressionError("x must have non-zero variance")

    slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

    predicted = slope * x + intercept
    residuals = y - predicted

    # Standard error of estimate
    if n > 2:
        se_estimate = np.sqrt(np.sum(residuals ** 2) / (n - 2))
    else:
        se_estimate = 0.0

    # Standard errors for slope and intercept
    x_mean = np.mean(x)
    ss_xx = np.sum((x - x_mean) ** 2)
    if ss_xx > 0:
        slope_se = se_estimate / np.sqrt(ss_xx)
        intercept_se = se_estimate * np.sqrt(1.0 / n + x_mean ** 2 / ss_xx)
    else:
        slope_se = 0.0
        intercept_se = 0.0

    r_squared = float(r_value ** 2)

    return LinearRegressionResult(
        slope=float(slope),
        intercept=float(intercept),
        r_squared=r_squared,
        slope_standard_error=float(slope_se),
        intercept_standard_error=float(intercept_se),
        residuals=tuple(float(r) for r in residuals),
        predicted=tuple(float(p) for p in predicted),
        point_count=n,
    )