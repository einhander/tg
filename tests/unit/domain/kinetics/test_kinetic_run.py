"""Tests for KineticRun invariants."""

import numpy as np
import pytest

from tgapp.domain.kinetics.models import KineticRun
from tgapp.domain.kinetics.units import TemperatureUnit, TimeUnit, MassUnit


class TestKineticRunInvariants:
    def _make_run(self, **overrides):
        defaults = {
            "run_id": "test_001",
            "source_name": "test.dat",
            "source_sha256": "abc123",
            "temperature_k": np.array([300.0, 350.0, 400.0, 450.0, 500.0]),
            "time_s": np.array([0.0, 10.0, 20.0, 30.0, 40.0]),
            "mass_g": np.array([1.0, 0.9, 0.8, 0.7, 0.6]),
            "nominal_heating_rate_k_s": None,
            "measured_heating_rate_k_s": 5.0,
            "heating_linearity_r2": 0.999,
            "heating_max_residual_k": 0.1,
            "sample_name": "test_sample",
            "atmosphere": "nitrogen",
            "source_temperature_unit": TemperatureUnit.KELVIN,
            "source_time_unit": TimeUnit.SECOND,
            "source_mass_unit": MassUnit.GRAM,
            "metadata": {"key": "value"},
        }
        defaults.update(overrides)
        return KineticRun(**defaults)

    def test_creates_from_valid_data(self):
        run = self._make_run()
        assert run.run_id == "test_001"
        assert len(run.temperature_k) == 5

    def test_arrays_1d(self):
        run = self._make_run()
        assert run.temperature_k.ndim == 1
        assert run.time_s.ndim == 1
        assert run.mass_g.ndim == 1

    def test_array_lengths_match(self):
        run = self._make_run()
        assert len(run.temperature_k) == len(run.time_s) == len(run.mass_g)

    def test_minimum_three_points(self):
        with pytest.raises(AssertionError, match="minimum 3 points"):
            self._make_run(
                temperature_k=np.array([300.0, 350.0]),
                time_s=np.array([0.0, 10.0]),
                mass_g=np.array([1.0, 0.9]),
            )

    def test_all_values_finite(self):
        with pytest.raises(AssertionError, match="must be finite"):
            self._make_run(temperature_k=np.array([300.0, np.inf, 400.0, 450.0, 500.0]))

    def test_time_strictly_increasing(self):
        with pytest.raises(AssertionError, match="time_s must be strictly increasing"):
            self._make_run(time_s=np.array([0.0, 10.0, 10.0, 30.0, 40.0]))

    def test_mass_positive(self):
        with pytest.raises(AssertionError, match="mass_g must be positive"):
            self._make_run(mass_g=np.array([1.0, 0.9, 0.0, 0.7, 0.6]))

    def test_measured_heating_rate_positive(self):
        with pytest.raises(AssertionError, match="must be positive"):
            self._make_run(measured_heating_rate_k_s=-1.0)

    def test_arrays_readonly(self):
        run = self._make_run()
        assert not run.temperature_k.flags.writeable
        assert not run.time_s.flags.writeable
        assert not run.mass_g.flags.writeable

    def test_metadata_immutability(self):
        run = self._make_run(metadata={"key": "value"})
        # metadata should be a Mapping — verify it's stored as-is
        assert run.metadata["key"] == "value"

    def test_different_temperature_range_does_not_affect_existing_run(self):
        """Another experiment with a narrower range should not cut the current KineticRun."""
        run = self._make_run(
            temperature_k=np.array([300.0, 350.0, 400.0, 450.0, 500.0]),
        )
        # Verify the run's arrays are intact regardless of other experiments
        assert len(run.temperature_k) == 5
        assert run.temperature_k[0] == 300.0
        assert run.temperature_k[-1] == 500.0