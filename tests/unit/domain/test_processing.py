"""Tests for tgapp.domain.processing."""

from __future__ import annotations

import pandas as pd
import pytest

from tgapp.domain.models import ProcessingSettings, ThermogramFile
from tgapp.domain.processing import (
    compute_dmdt_trace,
    estimate_adjusted_difflag,
    process_thermograms,
    round_mean_frame,
)


class TestComputeDmdtTrace:
    """compute_dmdt_trace basic behavior."""

    def test_empty_frame(self):
        """Empty frame → NaN series."""
        result = compute_dmdt_trace(pd.DataFrame(), difflag=1, bins=100)
        assert len(result) == 100
        assert result.name == "dmdt"
        assert result.isna().all()

    def test_missing_mass_column(self):
        """No mass column → NaN series."""
        df = pd.DataFrame({"temp": [1.0, 2.0], "time": [0.0, 1.0]})
        result = compute_dmdt_trace(df, difflag=1, bins=2)
        assert result.isna().all()

    def test_basic_dmdt(self):
        """Linear mass loss → constant dmdt."""
        n = 10
        df = pd.DataFrame({
            "mass": [100.0 - i for i in range(n)],
            "time": [float(i) for i in range(n)],
        })
        result = compute_dmdt_trace(df, difflag=1, bins=n)
        # dmdt should be approximately -1.0 for most entries
        valid = result.dropna()
        assert len(valid) > 0
        assert valid.iloc[0] < 0  # mass decreasing


class TestEstimateAdjustedDifflag:
    """estimate_adjusted_difflag."""

    def test_empty_resampled(self):
        """No resampled frames → difflag=1."""
        result = estimate_adjusted_difflag([], bins=1000, difflag=1)
        assert result == 1

    def test_basic_adjustment(self):
        """Some resampled frames → adjusted difflag."""
        df = pd.DataFrame({"time": [0.0, 1.0, 2.0, 3.0]})
        resampled = [df]
        result = estimate_adjusted_difflag(resampled, bins=100, difflag=1)
        assert result >= 1


class TestRoundMeanFrame:
    """round_mean_frame."""

    def test_rounds_temp_and_mass(self):
        """Rounds temp to 2dp, mass to 3dp."""
        df = pd.DataFrame({
            "temp": [1.234567, 2.345678],
            "mass": [100.123456, 99.987654],
            "time": [0.123456, 1.234567],
            "deltatemp": [0.123456, 0.234567],
        })
        result = round_mean_frame(df)
        assert result["temp"].iloc[0] == pytest.approx(1.23, abs=0.01)
        assert result["mass"].iloc[0] == pytest.approx(100.123, abs=0.001)


class TestProcessThermograms:
    """process_thermograms integration-level test."""

    def test_basic_processing(self):
        """Process a simple thermogram → non-empty result."""
        n = 100
        df = pd.DataFrame({
            "Temperature": [25.0 + i for i in range(n)],
            "DeltaTemp": [0.0] * n,
            "Time": [float(i) for i in range(n)],
            "Mass": [100.0 - 0.1 * i for i in range(n)],
        })
        files = [ThermogramFile(name="test.dat", frame=df)]
        settings = ProcessingSettings(bins=50, sg_mode=False, mass_smoothing=1)
        result = process_thermograms(files, settings)
        assert not result.mean_frame.empty
        assert "temp" in result.mean_frame.columns
        assert "mass" in result.mean_frame.columns
        assert "deltatemp" in result.mean_frame.columns
        assert "dmdt" in result.mean_frame.columns
        assert result.heat_speed_text  # not empty