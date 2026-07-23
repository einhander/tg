"""Tests for physical unit models and conversions."""

import numpy as np
import pytest

from tgapp.domain.kinetics.units import (
    TemperatureUnit,
    TimeUnit,
    MassUnit,
    to_kelvin,
    to_seconds,
    to_grams,
)


class TestTemperatureUnit:
    def test_celsius_to_kelvin(self):
        assert to_kelvin(np.array([0.0]), TemperatureUnit.CELSIUS) == pytest.approx(273.15)
        assert to_kelvin(np.array([100.0]), TemperatureUnit.CELSIUS) == pytest.approx(373.15)

    def test_kelvin_passthrough(self):
        arr = np.array([300.0, 400.0, 500.0])
        assert np.array_equal(to_kelvin(arr, TemperatureUnit.KELVIN), arr)

    def test_array_operations(self):
        celsius = np.array([0.0, 25.0, 100.0])
        kelvin = to_kelvin(celsius, TemperatureUnit.CELSIUS)
        assert kelvin[0] == pytest.approx(273.15)
        assert kelvin[1] == pytest.approx(298.15)
        assert kelvin[2] == pytest.approx(373.15)


class TestTimeUnit:
    def test_minute_to_second(self):
        assert to_seconds(np.array([1.0]), TimeUnit.MINUTE) == pytest.approx(60.0)
        assert to_seconds(np.array([5.0]), TimeUnit.MINUTE) == pytest.approx(300.0)

    def test_second_passthrough(self):
        arr = np.array([10.0, 20.0, 30.0])
        assert np.array_equal(to_seconds(arr, TimeUnit.SECOND), arr)


class TestMassUnit:
    def test_milligram_to_gram(self):
        assert to_grams(np.array([1000.0]), MassUnit.MILLIGRAM) == pytest.approx(1.0)
        assert to_grams(np.array([500.0]), MassUnit.MILLIGRAM) == pytest.approx(0.5)

    def test_gram_passthrough(self):
        arr = np.array([1.0, 2.0, 3.0])
        assert np.array_equal(to_grams(arr, MassUnit.GRAM), arr)

    def test_percent_passthrough(self):
        arr = np.array([0.5, 1.0, 100.0])
        assert np.array_equal(to_grams(arr, MassUnit.PERCENT), arr)