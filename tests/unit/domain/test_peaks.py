"""Tests for tgapp.domain.peaks."""

from __future__ import annotations

import pandas as pd
import pytest

from tgapp.domain.models import PeakResult, ProcessingSettings
from tgapp.domain.peaks import (
    detect_peaks,
    detect_raw_plot_markers,
    detect_tg_inflection_markers,
    detect_trace_extrema,
)


class TestDetectPeaks:
    """detect_peaks top-level function."""

    def test_empty_frame(self):
        """Empty frame → no peaks."""
        df = pd.DataFrame(columns=list(["temp", "deltatemp", "dmdt"]))
        settings = ProcessingSettings()
        result = detect_peaks(df, settings)
        assert result == []

    def test_small_frame(self):
        """Frame with < 3 valid points → no peaks."""
        df = pd.DataFrame({
            "temp": [1.0, 2.0],
            "deltatemp": [0.1, 0.2],
            "dmdt": [0.01, 0.02],
        })
        settings = ProcessingSettings()
        result = detect_peaks(df, settings)
        assert result == []


class TestDetectTraceExtrema:
    """detect_trace_extrema behavior."""

    def test_empty_frame(self):
        """Empty frame → no extrema."""
        df = pd.DataFrame()
        result = detect_trace_extrema(df, "deltatemp", "dta", span=91)
        assert result == []

    def test_missing_columns(self):
        """Missing temp or y_column → no extrema."""
        df = pd.DataFrame({"mass": [1.0, 2.0]})
        result = detect_trace_extrema(df, "deltatemp", "dta", span=91)
        assert result == []

    def test_too_few_points(self):
        """< 3 valid points → no extrema."""
        df = pd.DataFrame({
            "temp": [1.0, 2.0],
            "deltatemp": [0.1, 0.2],
        })
        result = detect_trace_extrema(df, "deltatemp", "dta", span=91)
        assert result == []

    def test_with_prominent_peak(self):
        """Frame with a clear peak in deltatemp → detects it."""
        n = 100
        temps = list(range(n))
        # Create a clear peak at index 50
        dta = [0.0] * n
        dta[48] = 1.0
        dta[49] = 2.0
        dta[50] = 10.0  # peak
        dta[51] = 2.0
        dta[52] = 1.0
        df = pd.DataFrame({"temp": temps, "deltatemp": dta})
        result = detect_trace_extrema(df, "deltatemp", "dta", span=91, prominence_sigma=3.0)
        # Should detect at least one peak near temp=50
        assert len(result) >= 1


class TestDetectTgInflectionMarkers:
    """detect_tg_inflection_markers."""

    def test_empty_frame(self):
        """Empty frame → no markers."""
        result = detect_tg_inflection_markers(pd.DataFrame(), 5.0)
        assert result == []

    def test_too_few_points(self):
        """< 5 valid points → no markers."""
        df = pd.DataFrame({"temp": [1.0, 2.0, 3.0], "mass": [10.0, 9.0, 8.0]})
        result = detect_tg_inflection_markers(df, 5.0)
        assert result == []

    def test_missing_columns(self):
        """Missing temp or mass → no markers."""
        df = pd.DataFrame({"deltatemp": [0.1, 0.2]})
        result = detect_tg_inflection_markers(df, 5.0)
        assert result == []


class TestDetectRawPlotMarkers:
    """detect_raw_plot_markers."""

    def test_empty_frame(self):
        """Empty frame → no markers."""
        from tgapp.domain.models import ThermogramViewSettings
        result = detect_raw_plot_markers(pd.DataFrame(), ThermogramViewSettings())
        assert result == []

    def test_missing_temp(self):
        """Missing temp column → no markers."""
        from tgapp.domain.models import ThermogramViewSettings
        df = pd.DataFrame({"mass": [1.0, 2.0]})
        result = detect_raw_plot_markers(df, ThermogramViewSettings())
        assert result == []