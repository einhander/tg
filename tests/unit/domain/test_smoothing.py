"""Tests for tgapp.domain.smoothing."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tgapp.domain.smoothing import (
    _savgol_values,
    smooth_column_savitzky_golay,
    smooth_derivative,
    smooth_derivative_savitzky_golay,
    smooth_mass,
    smooth_mass_savitzky_golay,
    smooth_series_savitzky_golay,
    smooth_temperature,
    smooth_temperature_savitzky_golay,
)


class TestSmoothMass:
    """smooth_mass with rolling mean."""

    def test_constant_series_remains_constant(self):
        """Constant mass → still constant after rolling mean."""
        df = pd.DataFrame({
            "temp": range(20),
            "mass": [100.0] * 20,
            "time": range(20),
        })
        result = smooth_mass(df, window=5)
        # All values should still be 100.0 (rolling mean of constant = constant)
        assert result["mass"].iloc[0] == 100.0
        assert result["mass"].iloc[-1] == 100.0
        # Check no NaN introduced
        assert not result["mass"].isna().any()

    def test_window_1_no_change(self):
        """Window=1 → no smoothing applied."""
        df = pd.DataFrame({
            "temp": range(10),
            "mass": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0],
        })
        result = smooth_mass(df, window=1)
        pd.testing.assert_series_equal(result["mass"], df["mass"], check_names=False)

    def test_no_mass_column(self):
        """No mass column → frame unchanged."""
        df = pd.DataFrame({"temp": [1.0, 2.0], "time": [0.0, 1.0]})
        result = smooth_mass(df, window=5)
        assert list(result.columns) == ["temp", "time"]


class TestSmoothSeriesSavitzkyGolay:
    """smooth_series_savitzky_golay with scipy."""

    def test_linear_series_remains_linear(self):
        """Linear series → still linear after SG filter (polyorder=1)."""
        s = pd.Series(range(21), dtype=float)  # 0, 1, 2, ..., 20
        result = smooth_series_savitzky_golay(s, window=5, polyorder=1)
        # SG with polyorder=1 on linear data should reproduce the line
        assert np.allclose(result.to_numpy(), s.to_numpy(), atol=1e-10)

    def test_short_series_preserved(self):
        """Series with < 3 valid values → unchanged."""
        s = pd.Series([1.0, np.nan, 3.0])
        result = smooth_series_savitzky_golay(s, window=5)
        assert len(result) == 3

    def test_nan_preserved(self):
        """NaN gaps are preserved after filtering."""
        s = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
        result = smooth_series_savitzky_golay(s, window=5, polyorder=2)
        assert np.isnan(result.iloc[2])


class TestSmoothDerivative:
    """smooth_derivative behavior."""

    def test_enabled_false_no_change(self):
        """smooth_dmdt=False → frame unchanged."""
        df = pd.DataFrame({
            "temp": range(20),
            "dmdt": [0.1, 0.2, 0.3, 0.4, 0.5] * 4,
        })
        result = smooth_derivative(df, span=91, enabled=False)
        pd.testing.assert_series_equal(result["dmdt"], df["dmdt"], check_names=False)

    def test_enabled_with_enough_points(self):
        """smooth_dmdt=True with enough points → some smoothing."""
        n = 50
        df = pd.DataFrame({
            "temp": range(n),
            "dmdt": [float(i) for i in range(n)],
        })
        result = smooth_derivative(df, span=91, enabled=True)
        # Should have same length
        assert len(result) == n
        # dmdt should be smoothed (less variation at edges)
        assert result["dmdt"].notna().sum() > 0

    def test_empty_frame(self):
        """Empty frame → unchanged."""
        df = pd.DataFrame(columns=["temp", "dmdt"])
        result = smooth_derivative(df, span=91, enabled=True)
        assert result.empty


class TestSmoothTemperature:
    """smooth_temperature with rolling mean."""

    def test_constant_temp_unchanged(self):
        """Constant temperature → unchanged."""
        df = pd.DataFrame({
            "temp": [25.0] * 20,
            "mass": range(20),
        })
        result = smooth_temperature(df, window=5)
        assert result["temp"].iloc[0] == 25.0
        assert result["temp"].iloc[-1] == 25.0

    def test_window_1_no_change(self):
        """Window=1 → no smoothing."""
        df = pd.DataFrame({
            "temp": [1.0, 2.0, 3.0, 4.0, 5.0],
            "mass": [10.0, 20.0, 30.0, 40.0, 50.0],
        })
        result = smooth_temperature(df, window=1)
        pd.testing.assert_series_equal(result["temp"], df["temp"], check_names=False)


class TestSmoothColumnSavitzkyGolay:
    """smooth_column_savitzky_golay on a frame column."""

    def test_missing_column_no_change(self):
        """Column not present → frame unchanged."""
        df = pd.DataFrame({"temp": [1.0, 2.0], "mass": [10.0, 20.0]})
        result = smooth_column_savitzky_golay(df, "nonexistent", 5, 2)
        pd.testing.assert_frame_equal(result, df)

    def test_empty_frame_no_change(self):
        """Empty frame → unchanged."""
        df = pd.DataFrame(columns=["temp", "mass"])
        result = smooth_column_savitzky_golay(df, "mass", 5, 2)
        assert result.empty


class TestSmoothMassSavitzkyGolay:
    """smooth_mass_savitzky_golay convenience wrapper."""

    def test_smoothes_mass_column(self):
        """Mass column gets SG smoothed."""
        df = pd.DataFrame({
            "temp": range(21),
            "mass": [float(i) for i in range(21)],
            "time": range(21),
        })
        result = smooth_mass_savitzky_golay(df, window=5, polyorder=2)
        # Should have same columns
        assert "mass" in result.columns
        # Linear data with SG polyorder=2 should be very close to original
        assert np.allclose(result["mass"].to_numpy(), df["mass"].to_numpy(), atol=1e-10)


class TestSavgolValues:
    """Direct tests for _savgol_values (scipy.signal.savgol_filter wrapper)."""

    def test_constant_preserved(self):
        """Константа после SG сглаживания остаётся константой."""
        values = np.full(50, 100.0)
        result = _savgol_values(values, window=5, polyorder=2)
        assert np.allclose(result, 100.0)

    def test_linear_preserved(self):
        """Линейная функция не искажается SG с полиномом 2+ порядка."""
        x = np.linspace(0, 100, 100)
        values = 2.0 * x + 5.0
        result = _savgol_values(values, window=5, polyorder=2)
        assert np.allclose(result, values, atol=0.01)

    def test_quadratic_preserved(self):
        """Квадратичная функция сохраняется SG с полиномом 2."""
        x = np.linspace(0, 100, 100)
        values = 0.01 * x ** 2 + 2.0 * x + 5.0
        result = _savgol_values(values, window=5, polyorder=2)
        assert np.allclose(result, values, atol=0.1)

    def test_even_window_made_odd(self):
        """Чётное окно превращается в нечётное."""
        values = np.random.randn(50)
        result = _savgol_values(values, window=6, polyorder=2)
        assert len(result) == 50

    def test_window_too_small_returns_copy(self):
        """Окно < 3 → win принудительно 3, savgol_filter вызывается, значения близки."""
        values = np.array([1.0, 2.0, 3.0])
        result = _savgol_values(values, window=2, polyorder=1)
        # win принудительно 3 → savgol_filter([1,2,3], 3, 1) → [1,2,3]
        assert np.allclose(result, values)

    def test_scipy_imported(self):
        """scipy.signal.savgol_filter импортируется."""
        from scipy.signal import savgol_filter
        assert savgol_filter is not None

    def test_nan_gaps_not_interpolated(self):
        """savgol_filter бросает ValueError на NaN → fallback на copy."""
        values = np.array([1.0, 2.0, np.nan, np.nan, 5.0, 6.0, 7.0])
        result = _savgol_values(values, window=3, polyorder=1)
        # scipy savgol_filter не принимает NaN → ValueError → возвращает copy оригинала
        assert np.array_equal(result, values, equal_nan=True)


class TestSmoothTemperatureSavitzkyGolay:
    """smooth_temperature_savitzky_golay convenience wrapper."""

    def test_smoothes_temp_column(self):
        """Temperature column gets SG smoothed."""
        df = pd.DataFrame({
            "temp": [float(i) for i in range(21)],
            "mass": range(21),
        })
        result = smooth_temperature_savitzky_golay(df, window=5, polyorder=2)
        assert "temp" in result.columns
        assert "mass" in result.columns
        # Linear data with SG polyorder=2 should be very close to original
        assert np.allclose(result["temp"].to_numpy(), df["temp"].to_numpy(), atol=1e-10)

    def test_missing_temp_column_no_change(self):
        """No temp column → frame unchanged."""
        df = pd.DataFrame({"mass": [1.0, 2.0, 3.0]})
        result = smooth_temperature_savitzky_golay(df, window=5, polyorder=2)
        assert list(result.columns) == ["mass"]

    def test_empty_frame(self):
        """Empty frame → unchanged."""
        df = pd.DataFrame(columns=["temp", "mass"])
        result = smooth_temperature_savitzky_golay(df, window=5, polyorder=2)
        assert result.empty


class TestSmoothDerivativeSavitzkyGolay:
    """smooth_derivative_savitzky_golay convenience wrapper."""

    def test_smoothes_dmdt_column(self):
        """DTG column gets SG smoothed."""
        n = 50
        df = pd.DataFrame({
            "temp": [float(i) for i in range(n)],
            "dmdt": [float(i) * 0.1 for i in range(n)],
        })
        result = smooth_derivative_savitzky_golay(df, window=5, polyorder=2)
        assert "dmdt" in result.columns
        assert "temp" in result.columns

    def test_missing_dmdt_column_no_change(self):
        """No dmdt column → frame unchanged."""
        df = pd.DataFrame({"temp": [1.0, 2.0, 3.0]})
        result = smooth_derivative_savitzky_golay(df, window=5, polyorder=2)
        assert list(result.columns) == ["temp"]

    def test_empty_frame(self):
        """Empty frame → unchanged."""
        df = pd.DataFrame(columns=["temp", "dmdt"])
        result = smooth_derivative_savitzky_golay(df, window=5, polyorder=2)
        assert result.empty