"""Tests for tgapp.domain.processing — per-run DTG computation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tgapp.domain.processing import (
    average_dmdt_traces,
    compute_dmdt_per_run,
)


class TestComputeDmdtPerRun:
    def test_linear_mass_decrease(self):
        """m(t) = 100 - 0.5t → dm/dt = -0.5"""
        time = np.linspace(0, 200, 100)
        mass = 100.0 - 0.5 * time
        frame = pd.DataFrame({"time": time, "mass": mass})
        dmdt = compute_dmdt_per_run(frame)
        central = dmdt.iloc[10:-10]
        assert np.allclose(central, -0.5, atol=0.01)

    def test_constant_mass(self):
        """m(t) = 100 → dm/dt = 0"""
        time = np.linspace(0, 100, 50)
        mass = np.full(50, 100.0)
        frame = pd.DataFrame({"time": time, "mass": mass})
        dmdt = compute_dmdt_per_run(frame)
        assert np.allclose(dmdt, 0.0, atol=1e-10)

    def test_empty_frame(self):
        frame = pd.DataFrame({"time": [], "mass": []})
        dmdt = compute_dmdt_per_run(frame)
        assert len(dmdt) > 0
        assert all(np.isnan(dmdt))

    def test_missing_columns(self):
        frame = pd.DataFrame({"temp": [1, 2, 3]})
        dmdt = compute_dmdt_per_run(frame)
        assert len(dmdt) > 0

    def test_quadratic_mass(self):
        """m(t) = 100 - 0.01t² → dm/dt = -0.02t"""
        time = np.linspace(0, 100, 100)
        mass = 100.0 - 0.01 * time ** 2
        frame = pd.DataFrame({"time": time, "mass": mass})
        dmdt = compute_dmdt_per_run(frame)
        expected = -0.02 * time
        central = dmdt.iloc[5:-5]
        expected_central = expected[5:-5]
        assert np.allclose(central, expected_central, atol=0.01)


class TestAverageDmdtTraces:
    def test_single_trace(self):
        series = [pd.Series([-0.5, -0.5, -0.5, -0.5], name="dmdt")]
        result = average_dmdt_traces(series)
        assert len(result) == 4
        assert np.allclose(result, -0.5)

    def test_two_identical_traces(self):
        s1 = pd.Series([-0.5, -0.5, -0.5, -0.5], name="dmdt")
        s2 = pd.Series([-0.5, -0.5, -0.5, -0.5], name="dmdt")
        result = average_dmdt_traces([s1, s2])
        assert np.allclose(result, -0.5)

    def test_empty_list(self):
        result = average_dmdt_traces([])
        assert len(result) > 0

    def test_different_lengths_interpolated(self):
        s1 = pd.Series([-0.5, -0.5, -0.5], name="dmdt")
        s2 = pd.Series([-0.4, -0.4, -0.4, -0.4, -0.4], name="dmdt")
        result = average_dmdt_traces([s1, s2])
        assert len(result) == 5
        assert np.allclose(result, -0.45, atol=0.01)