"""Tests for linear regression."""

import numpy as np
import pytest

from tgapp.domain.kinetics.errors import RegressionError
from tgapp.domain.kinetics.regression import linear_regression


class TestLinearRegression:
    def test_perfect_line(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = 2.0 * x + 3.0
        result = linear_regression(x, y)
        assert result.slope == pytest.approx(2.0)
        assert result.intercept == pytest.approx(3.0)
        assert result.r_squared == pytest.approx(1.0)

    def test_minimum_points(self):
        x = np.array([1.0, 2.0, 3.0])
        y = np.array([2.0, 4.0, 6.0])
        result = linear_regression(x, y)
        assert result.point_count == 3

    def test_too_few_points(self):
        with pytest.raises(RegressionError, match="Minimum 3 points"):
            linear_regression(np.array([1.0, 2.0]), np.array([3.0, 4.0]))

    def test_mismatched_lengths(self):
        with pytest.raises(RegressionError, match="same length"):
            linear_regression(np.array([1.0, 2.0, 3.0]), np.array([4.0, 5.0]))

    def test_non_finite_values(self):
        with pytest.raises(RegressionError, match="finite"):
            linear_regression(np.array([1.0, np.nan, 3.0]), np.array([2.0, 4.0, 6.0]))

    def test_zero_variance_x(self):
        with pytest.raises(RegressionError, match="non-zero variance"):
            linear_regression(np.array([5.0, 5.0, 5.0]), np.array([1.0, 2.0, 3.0]))

    def test_residuals_and_predicted(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = 2.0 * x + 3.0
        result = linear_regression(x, y)
        assert len(result.residuals) == 5
        assert len(result.predicted) == 5
        # Perfect fit: residuals should be ~0
        assert all(abs(r) < 1e-10 for r in result.residuals)

    def test_deterministic(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = 2.0 * x + 3.0 + np.array([0.1, -0.1, 0.05, -0.05, 0.0])
        r1 = linear_regression(x, y)
        r2 = linear_regression(x, y)
        assert r1.slope == r2.slope
        assert r1.intercept == r2.intercept
        assert r1.r_squared == r2.r_squared

    def test_standard_errors_computed(self):
        x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        y = 2.0 * x + 3.0 + np.array([0.1, -0.1, 0.05, -0.05, 0.0])
        result = linear_regression(x, y)
        assert result.slope_standard_error > 0
        assert result.intercept_standard_error > 0