"""Tests for heating program calculation."""

import numpy as np
import pytest

from tgapp.domain.kinetics.errors import HeatingProgramError
from tgapp.domain.kinetics.heating_program import calculate_heating_program
from tgapp.domain.kinetics.models import HeatingValidationSettings


class TestHeatingProgram:
    def _make_linear_data(self, beta_K_per_min: float = 10.0, n: int = 100, T0: float = 300.0):
        """Generate perfectly linear T(t) data."""
        beta_K_per_s = beta_K_per_min / 60.0
        time_s = np.linspace(0, 3000, n)
        temperature_k = T0 + beta_K_per_s * time_s
        return temperature_k, time_s

    def test_basic_calculation(self):
        temp, time = self._make_linear_data(beta_K_per_min=10.0)
        hp = calculate_heating_program(temp, time)
        assert hp.beta_k_s == pytest.approx(10.0 / 60.0, abs=1e-6)
        assert hp.intercept_k == pytest.approx(300.0, abs=1e-6)
        assert hp.r_squared == pytest.approx(1.0, abs=1e-10)
        assert hp.point_count == 100

    def test_minimum_points(self):
        temp, time = self._make_linear_data(n=3)
        hp = calculate_heating_program(temp, time)
        assert hp.point_count == 3

    def test_too_few_points(self):
        temp = np.array([300.0, 310.0])
        time = np.array([0.0, 10.0])
        with pytest.raises(HeatingProgramError, match="Minimum 3 points"):
            calculate_heating_program(temp, time)

    def test_non_finite_values(self):
        temp = np.array([300.0, np.inf, 400.0])
        time = np.array([0.0, 10.0, 20.0])
        with pytest.raises(HeatingProgramError, match="non-finite"):
            calculate_heating_program(temp, time)

    def test_non_increasing_time(self):
        temp = np.array([300.0, 350.0, 400.0])
        time = np.array([0.0, 10.0, 10.0])
        with pytest.raises(HeatingProgramError, match="strictly increasing"):
            calculate_heating_program(temp, time)

    def test_zero_temperature_range(self):
        temp = np.array([300.0, 300.0, 300.0])
        time = np.array([0.0, 10.0, 20.0])
        with pytest.raises(HeatingProgramError, match="non-zero"):
            calculate_heating_program(temp, time)

    def test_negative_heating_rate(self):
        # Range positive (300→310) but regression slope negative (cooling trend)
        temp = np.array([300.0, 200.0, 150.0, 100.0, 310.0])
        time = np.array([0.0, 5.0, 10.0, 15.0, 20.0])
        settings = HeatingValidationSettings(minimum_r_squared=0.0)
        with pytest.raises(HeatingProgramError, match="positive"):
            calculate_heating_program(temp, time, settings)

    def test_low_r_squared_rejection(self):
        """Non-linear temperature profile should be rejected."""
        time = np.linspace(0, 3000, 100)
        # Quadratic temperature — not linear
        temp = 300.0 + 0.001 * time ** 2
        settings = HeatingValidationSettings(minimum_r_squared=0.9999)
        with pytest.raises(HeatingProgramError, match="linearity"):
            calculate_heating_program(temp, time, settings)

    def test_custom_settings(self):
        temp, time = self._make_linear_data()
        settings = HeatingValidationSettings(minimum_r_squared=0.99)
        hp = calculate_heating_program(temp, time, settings)
        assert hp.r_squared == pytest.approx(1.0, abs=1e-10)