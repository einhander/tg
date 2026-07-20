"""Tests for tgapp.domain.processing."""

from __future__ import annotations

import pandas as pd
import pytest

from tgapp.domain.models import ProcessingSettings, ThermogramFile
from tgapp.domain.processing import (
    process_thermograms,
    round_mean_frame,
)


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