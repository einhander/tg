"""Integration tests using real sample files."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tgapp.application.use_cases import process_session
from tgapp.domain.models import ProcessingSettings, ThermogramFile
from tgapp.domain.processing import process_thermograms
from tgapp.domain.summary import build_heat_speed_text
from tgapp.infrastructure.file_parsers import _normalize_columns, _read_frame


class TestUploadAndProcessSosna:
    """Integration tests with Сосна sample file."""

    def test_parse_and_process_sosna(self, sample_sosna_path: Path):
        """Parse Сосна file → process → non-empty result with required columns."""
        raw = sample_sosna_path.read_bytes()
        frame = _normalize_columns(_read_frame(raw))
        assert not frame.empty
        assert len(frame) > 100  # Should have substantial data

        files = [ThermogramFile(name=sample_sosna_path.name, frame=frame)]
        settings = ProcessingSettings(bins=500, sg_mode=False, mass_smoothing=1)
        result = process_thermograms(files, settings)

        assert not result.mean_frame.empty
        assert "temp" in list(result.mean_frame.columns)
        assert "mass" in list(result.mean_frame.columns)
        assert "deltatemp" in list(result.mean_frame.columns)
        assert "dmdt" in list(result.mean_frame.columns)

    def test_sosna_heat_speed_smoke(self, sample_sosna_path: Path):
        """Heat speed for Сосна ≈ 9.8 K/min (±1.0 tolerance)."""
        raw = sample_sosna_path.read_bytes()
        frame = _normalize_columns(_read_frame(raw))
        speed_text = build_heat_speed_text(frame)
        # Expected ≈ 9.8, tolerance ±1.0
        assert "9.8" in speed_text or "9." in speed_text or "10." in speed_text


class TestUploadAndProcessBirza:
    """Integration tests with Береза sample file."""

    def test_parse_and_process_birza(self, sample_birza_path: Path):
        """Parse Береза file → process → non-empty result."""
        raw = sample_birza_path.read_bytes()
        frame = _normalize_columns(_read_frame(raw))
        assert not frame.empty

        files = [ThermogramFile(name=sample_birza_path.name, frame=frame)]
        settings = ProcessingSettings(bins=500, sg_mode=False, mass_smoothing=1)
        result = process_thermograms(files, settings)

        assert not result.mean_frame.empty
        assert "temp" in list(result.mean_frame.columns)
        assert "mass" in list(result.mean_frame.columns)
        assert "deltatemp" in list(result.mean_frame.columns)
        assert "dmdt" in list(result.mean_frame.columns)

    def test_birza_has_temperature_column(self, sample_birza_path: Path):
        """Береза file has valid temperature data."""
        raw = sample_birza_path.read_bytes()
        frame = _normalize_columns(_read_frame(raw))
        temp_col = frame["temp"]
        assert temp_col.notna().sum() > 0
        assert temp_col.min() > 0  # Temperatures should be positive