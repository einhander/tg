"""Tests for tgapp.domain.thermogram."""

from __future__ import annotations

import pandas as pd
import pytest

from tgapp.domain.models import ThermogramFile
from tgapp.domain.thermogram import (
    combine_thermograms,
    compute_mean_traces,
    normalize_thermogram_frame,
    resample_thermogram,
)


class TestNormalizeThermogramFrame:
    """normalize_thermogram_frame basic behavior."""

    def test_normalizes_four_columns(self):
        """A DataFrame with 4 columns gets normalized."""
        df = pd.DataFrame({
            "temp": [25.0, 30.0, 35.0],
            "deltatemp": [0.1, 0.2, 0.3],
            "time": [0.0, 1.0, 2.0],
            "mass": [100.0, 99.0, 98.0],
        })
        result = normalize_thermogram_frame(df)
        assert list(result.columns) == ["temp", "deltatemp", "time", "mass"]
        assert len(result) == 3
        assert result["temp"].iloc[0] == 25.0
        assert result["mass"].iloc[2] == 98.0

    def test_missing_columns_remain_nan(self):
        """Columns not present in input remain NaN (no fillna)."""
        df = pd.DataFrame({"temp": [1.0, 2.0], "mass": [10.0, 20.0]})
        result = normalize_thermogram_frame(df)
        assert list(result.columns) == ["temp", "deltatemp", "time", "mass"]
        assert pd.isna(result["deltatemp"].iloc[0])
        assert pd.isna(result["time"].iloc[0])

    def test_non_numeric_becomes_nan(self):
        """Non-numeric values become NaN after coercion (no fillna)."""
        df = pd.DataFrame({
            "temp": ["abc", "10.0"],
            "mass": ["100.0", "200.0"],
        })
        result = normalize_thermogram_frame(df)
        # "abc" → NaN, no ffill/bfill/fillna
        assert pd.isna(result["temp"].iloc[0])
        assert result["temp"].iloc[1] == 10.0


class TestResampleThermogram:
    """resample_thermogram binning and interpolation."""

    def test_downsample_1000_to_500(self):
        """1000 points → 500 via binning."""
        df = pd.DataFrame({
            "temp": range(1000),
            "deltatemp": range(1000),
            "time": range(1000),
            "mass": range(1000),
        })
        result = resample_thermogram(df, bins=500)
        assert len(result) == 500

    def test_upsample_50_to_500(self):
        """50 points → 500 via interpolation."""
        df = pd.DataFrame({
            "temp": range(50),
            "deltatemp": range(50),
            "time": range(50),
            "mass": range(50),
        })
        result = resample_thermogram(df, bins=500)
        assert len(result) == 500

    def test_empty_frame_returns_empty(self):
        """Empty input returns empty with correct columns."""
        df = pd.DataFrame(columns=["temp", "deltatemp", "time", "mass"])
        result = resample_thermogram(df, bins=100)
        assert result.empty
        assert list(result.columns) == ["temp", "deltatemp", "time", "mass"]


class TestCombineThermograms:
    """combine_thermograms merges multiple files."""

    def test_combine_two_files(self):
        """Two files → combined frame with series column."""
        files = [
            ThermogramFile(name="file1", frame=pd.DataFrame({
                "Temperature": [1.0, 2.0], "Mass": [10.0, 20.0],
            })),
            ThermogramFile(name="file2", frame=pd.DataFrame({
                "Temperature": [3.0, 4.0], "Mass": [30.0, 40.0],
            })),
        ]
        result = combine_thermograms(files)
        assert len(result) == 4
        assert "series" in list(result.columns)
        assert set(result["series"].unique()) == {"file1", "file2"}

    def test_combine_empty_list(self):
        """No files → empty frame with correct columns."""
        result = combine_thermograms([])
        assert result.empty
        assert "series" in list(result.columns)


class TestComputeMeanTraces:
    """compute_mean_traces averages multiple frames."""

    def test_identical_frames_yield_same_mean(self):
        """Two identical frames → mean equals original."""
        df = pd.DataFrame({
            "temp": [1.0, 2.0, 3.0],
            "deltatemp": [0.1, 0.2, 0.3],
            "time": [0.0, 1.0, 2.0],
            "mass": [100.0, 99.0, 98.0],
        })
        result = compute_mean_traces([df, df])
        pd.testing.assert_frame_equal(result, df, check_dtype=False)

    def test_mean_of_two_different_frames(self):
        """Mean of [1,2] and [3,4] → [2,3]."""
        df1 = pd.DataFrame({
            "temp": [1.0, 2.0],
            "deltatemp": [0.0, 0.0],
            "time": [0.0, 1.0],
            "mass": [10.0, 20.0],
        })
        df2 = pd.DataFrame({
            "temp": [3.0, 4.0],
            "deltatemp": [0.0, 0.0],
            "time": [0.0, 1.0],
            "mass": [30.0, 40.0],
        })
        result = compute_mean_traces([df1, df2])
        assert result["temp"].iloc[0] == 2.0
        assert result["temp"].iloc[1] == 3.0
        assert result["mass"].iloc[0] == 20.0
        assert result["mass"].iloc[1] == 30.0

    def test_empty_list_returns_empty(self):
        """No frames → empty result."""
        result = compute_mean_traces([])
        assert result.empty