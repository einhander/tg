"""Tests for tgapp.domain.summary."""

from __future__ import annotations

import pandas as pd
import pytest

from tgapp.domain.models import PeakResult, ThermogramFile
from tgapp.domain.summary import (
    build_effect_text,
    build_heat_speed_text,
    build_summary,
)


class TestBuildHeatSpeedText:
    """build_heat_speed_text with known data."""

    def test_linear_T_t_beta_10(self):
        """T(t) = 25 + 10t → speed = T(last_time)/last_time."""
        # Use T0=0 so speed = beta exactly
        df = pd.DataFrame({
            "temp": [0.0, 10.0, 20.0, 30.0, 40.0],
            "time": [0.0, 1.0, 2.0, 3.0, 4.0],
        })
        text = build_heat_speed_text(df)
        # last temp=40, last time=4 → 40/4 = 10.0
        assert "10.0" in text

    def test_speed_9_8(self):
        """Known speed 9.8 K/min."""
        df = pd.DataFrame({
            "temp": [25.0, 123.0],
            "time": [0.0, 10.0],
        })
        text = build_heat_speed_text(df)
        # (123-25)/10 = 9.8
        assert "9.8" in text

    def test_empty_frame(self):
        """Empty frame → unavailable."""
        df = pd.DataFrame()
        text = build_heat_speed_text(df)
        assert "недоступна" in text

    def test_missing_columns(self):
        """Missing temp or time → unavailable."""
        df = pd.DataFrame({"mass": [100.0]})
        text = build_heat_speed_text(df)
        assert "недоступна" in text

    def test_zero_time(self):
        """Zero time → unavailable."""
        df = pd.DataFrame({"temp": [100.0], "time": [0.0]})
        text = build_heat_speed_text(df)
        assert "недоступна" in text


class TestBuildEffectText:
    """build_effect_text behavior."""

    def test_no_selection(self):
        """No xmin/xmax → prompt to select."""
        df = pd.DataFrame({"temp": [1.0, 2.0], "deltatemp": [0.1, 0.2]})
        text = build_effect_text(df, None, None, init_mass=1.0)
        assert "выделите температурный интервал" in text

    def test_empty_frame(self):
        """Empty frame → prompt."""
        text = build_effect_text(pd.DataFrame(), 10.0, 20.0, init_mass=1.0)
        assert "выделите температурный интервал" in text

    def test_missing_columns(self):
        """Missing required columns → prompt."""
        df = pd.DataFrame({"temp": [1.0]})
        text = build_effect_text(df, 1.0, 2.0, init_mass=1.0)
        assert "выделите температурный интервал" in text


class TestBuildSummary:
    """build_summary with various inputs."""

    def test_empty_frame(self):
        """Empty frame → basic summary."""
        files = [ThermogramFile(name="test.dat")]
        result = build_summary(files, pd.DataFrame(), [])
        assert result.metrics["thermogram_count"] == 1
        assert result.metrics["processed_rows"] == 0
        assert result.metrics["peak_count"] == 0

    def test_with_peaks(self):
        """Summary includes peak count."""
        files = [ThermogramFile(name="test.dat")]
        frame = pd.DataFrame({"temp": [1.0, 2.0], "mass": [100.0, 99.0]})
        peaks = [PeakResult(x=1.0, y=0.5, label="1.0", kind="dtg", extremum="peak")]
        result = build_summary(files, frame, peaks)
        assert result.metrics["peak_count"] == 1
        assert any("пиков: 1" in line for line in result.lines)