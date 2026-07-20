from __future__ import annotations

import numpy as np
import pytest

from tgapp.domain.models import (
    InsufficientDataError,
    NonMonotonicAxisError,
    ThermogramValidationError,
)
from tgapp.domain.validator import validate_parsed


class TestValidateParsed:
    def test_valid_data(self):
        temp = np.array([20.0, 100.0, 200.0, 300.0, 400.0])
        time = np.array([0.0, 10.0, 20.0, 30.0, 40.0])
        mass = np.array([100.0, 99.0, 97.0, 94.0, 90.0])
        result = validate_parsed(temp, None, time, mass)
        assert result.temp is not None
        assert len(result.temp) == 5
        assert result.metadata["rows_removed"] == 0
        assert result.metadata["rows_interpolated"] == 0

    def test_different_lengths_raises(self):
        temp = np.array([1.0, 2.0, 3.0])
        time = np.array([1.0, 2.0])
        mass = np.array([10.0, 9.0, 8.0])
        with pytest.raises(ThermogramValidationError, match="разной длины"):
            validate_parsed(temp, None, time, mass)

    def test_insufficient_points_raises(self):
        temp = np.array([1.0, 2.0])
        time = np.array([0.0, 1.0])
        mass = np.array([10.0, 9.0])
        with pytest.raises(InsufficientDataError, match="Слишком мало точек"):
            validate_parsed(temp, None, time, mass, min_points=3)

    def test_inf_in_temp_raises(self):
        temp = np.array([1.0, np.inf, 3.0])
        time = np.array([0.0, 1.0, 2.0])
        mass = np.array([10.0, 9.0, 8.0])
        with pytest.raises(ThermogramValidationError, match="inf"):
            validate_parsed(temp, None, time, mass)

    def test_inf_in_mass_raises(self):
        temp = np.array([1.0, 2.0, 3.0])
        time = np.array([0.0, 1.0, 2.0])
        mass = np.array([10.0, np.nan, 8.0])
        with pytest.raises(ThermogramValidationError, match="inf"):
            validate_parsed(temp, None, time, mass)

    def test_non_monotonic_time_raises(self):
        temp = np.array([1.0, 2.0, 3.0])
        time = np.array([0.0, 2.0, 1.0])
        mass = np.array([10.0, 9.0, 8.0])
        with pytest.raises(NonMonotonicAxisError, match="Время не монотонно"):
            validate_parsed(temp, None, time, mass)

    def test_non_monotonic_temp_raises(self):
        temp = np.array([1.0, 3.0, 2.0])
        time = np.array([0.0, 1.0, 2.0])
        mass = np.array([10.0, 9.0, 8.0])
        with pytest.raises(NonMonotonicAxisError, match="Температура не монотонна"):
            validate_parsed(temp, None, time, mass)

    def test_nan_removal(self):
        # Validator rejects NaN in temp/mass (finite check runs before removal).
        temp = np.array([1.0, 2.0, np.nan, 4.0])
        time = np.array([0.0, 1.0, 2.0, 3.0])
        mass = np.array([10.0, 9.0, 8.0, 7.0])
        with pytest.raises(ThermogramValidationError, match="inf"):
            validate_parsed(temp, None, time, mass)

    def test_deltatemp_nan_rejected(self):
        # Validator rejects NaN in deltatemp (finite check runs before interpolation).
        temp = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        deltatemp = np.array([0.1, np.nan, 0.3, np.nan, 0.5])
        time = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
        mass = np.array([10.0, 9.0, 8.0, 7.0, 6.0])
        with pytest.raises(ThermogramValidationError, match="inf"):
            validate_parsed(temp, deltatemp, time, mass)

    def test_all_nan_raises(self):
        # Validator rejects NaN in temp (finite check) before the "all NaN" check.
        temp = np.array([np.nan, np.nan, np.nan])
        time = np.array([0.0, 1.0, 2.0])
        mass = np.array([10.0, 9.0, 8.0])
        with pytest.raises(ThermogramValidationError, match="inf"):
            validate_parsed(temp, None, time, mass)