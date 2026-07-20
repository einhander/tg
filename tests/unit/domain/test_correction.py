"""Tests for tgapp.domain.correction — temperature-grid interpolation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from tgapp.domain.correction import (
    apply_correction_to_aligned,
    interpolate_correction_on_grid,
)
from tgapp.domain.models import (
    AlignedThermogram,
    CorrectionFile,
    CorrectionRangeError,
)


class TestInterpolateCorrectionOnGrid:
    """interpolate_correction_on_grid."""

    def test_perfect_coverage(self):
        """Correction покрывает temperature_grid точно."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 200.0, 300.0, 400.0, 500.0],
                "deltatemp": [0.1, 0.2, 0.3, 0.2, 0.1],
            }),
        )
        temperature_grid = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        result = interpolate_correction_on_grid(correction, temperature_grid)
        assert len(result) == 5
        assert np.allclose(result, [0.1, 0.2, 0.3, 0.2, 0.1])

    def test_larger_grid(self):
        """Correction с меньшим количеством точек интерполируется на большую сетку."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 300.0, 500.0],
                "deltatemp": [0.1, 0.3, 0.1],
            }),
        )
        temperature_grid = np.linspace(100.0, 500.0, 5)
        result = interpolate_correction_on_grid(correction, temperature_grid)
        assert len(result) == 5
        assert np.allclose(result, [0.1, 0.2, 0.3, 0.2, 0.1])

    def test_no_coverage_raises(self):
        """Correction не покрывает temperature_grid → CorrectionRangeError."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 200.0, 300.0],
                "deltatemp": [0.1, 0.2, 0.1],
            }),
        )
        temperature_grid = np.array([50.0, 100.0, 200.0, 300.0, 400.0])
        with pytest.raises(CorrectionRangeError, match="does not cover"):
            interpolate_correction_on_grid(correction, temperature_grid)

    def test_empty_correction_raises(self):
        """Пустой correction → CorrectionRangeError."""
        correction = CorrectionFile(name="correction", frame=pd.DataFrame())
        temperature_grid = np.array([100.0, 200.0, 300.0])
        with pytest.raises(CorrectionRangeError, match="empty"):
            interpolate_correction_on_grid(correction, temperature_grid)

    def test_nan_points_removed(self):
        """Точки с NaN в temp или deltatemp удаляются."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, np.nan, 300.0, 400.0, 500.0],
                "deltatemp": [0.1, 0.2, 0.3, 0.2, 0.1],
            }),
        )
        temperature_grid = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        result = interpolate_correction_on_grid(correction, temperature_grid)
        assert len(result) == 5

    def test_insufficient_points_raises(self):
        """Менее 2 валидных точек → CorrectionRangeError."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, np.nan],
                "deltatemp": [0.1, 0.2],
            }),
        )
        temperature_grid = np.array([100.0, 200.0])
        with pytest.raises(CorrectionRangeError, match="insufficient"):
            interpolate_correction_on_grid(correction, temperature_grid)

    def test_sorted_if_unsorted(self):
        """Неотсортированная температура коррекции сортируется."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [300.0, 100.0, 200.0, 500.0, 400.0],
                "deltatemp": [0.3, 0.1, 0.2, 0.5, 0.4],
            }),
        )
        temperature_grid = np.array([100.0, 200.0, 300.0, 400.0, 500.0])
        result = interpolate_correction_on_grid(correction, temperature_grid)
        assert np.allclose(result, [0.1, 0.2, 0.3, 0.4, 0.5])

    def test_larger_correction_range(self):
        """Correction шире grid — лишние точки игнорируются."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [0.0, 100.0, 200.0, 300.0, 600.0],
                "deltatemp": [0.0, 0.1, 0.2, 0.3, 0.4],
            }),
        )
        temperature_grid = np.array([100.0, 200.0, 300.0])
        result = interpolate_correction_on_grid(correction, temperature_grid)
        assert np.allclose(result, [0.1, 0.2, 0.3])

    def test_string_temps_converted(self):
        """Температура в строках конвертируется в float."""
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": ["100.0", "200.0", "300.0"],
                "deltatemp": ["0.1", "0.2", "0.3"],
            }),
        )
        temperature_grid = np.array([100.0, 200.0, 300.0])
        result = interpolate_correction_on_grid(correction, temperature_grid)
        assert np.allclose(result, [0.1, 0.2, 0.3])


class TestApplyCorrectionToAligned:
    """apply_correction_to_aligned."""

    def test_single_aligned(self):
        """Коррекция применяется к одной термограмме."""
        aligned = [AlignedThermogram(
            name="test",
            temp=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            deltatemp=np.array([0.5, 0.6, 0.7, 0.6, 0.5]),
            time=np.array([0.0, 10.0, 20.0, 30.0, 40.0]),
            mass=np.array([100.0, 99.0, 97.0, 94.0, 90.0]),
            temperature_grid=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            metadata={},
        )]
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 200.0, 300.0, 400.0, 500.0],
                "deltatemp": [0.1, 0.2, 0.3, 0.2, 0.1],
            }),
        )
        result = apply_correction_to_aligned(aligned, correction)
        assert len(result) == 1
        assert np.allclose(result[0].deltatemp, [0.6, 0.8, 1.0, 0.8, 0.6])

    def test_no_correction_applied(self):
        """Пустой список → пустой список."""
        correction = CorrectionFile(name="correction", frame=pd.DataFrame())
        result = apply_correction_to_aligned([], correction)
        assert result == []

    def test_correction_skipped_on_error(self):
        """Коррекция не покрывает диапазон → термограммы без изменений."""
        aligned = [AlignedThermogram(
            name="test",
            temp=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            deltatemp=np.array([0.5, 0.6, 0.7, 0.6, 0.5]),
            time=np.array([0.0, 10.0, 20.0, 30.0, 40.0]),
            mass=np.array([100.0, 99.0, 97.0, 94.0, 90.0]),
            temperature_grid=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            metadata={},
        )]
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [600.0, 700.0, 800.0],
                "deltatemp": [0.1, 0.2, 0.1],
            }),
        )
        result = apply_correction_to_aligned(aligned, correction)
        assert len(result) == 1
        assert np.allclose(result[0].deltatemp, [0.5, 0.6, 0.7, 0.6, 0.5])

    def test_multiple_aligned(self):
        """Коррекция применяется к нескольким термограммам."""
        aligned = [
            AlignedThermogram(
                name="t1",
                temp=np.array([100.0, 200.0, 300.0]),
                deltatemp=np.array([0.5, 0.6, 0.7]),
                time=np.array([0.0, 10.0, 20.0]),
                mass=np.array([100.0, 99.0, 98.0]),
                temperature_grid=np.array([100.0, 200.0, 300.0]),
                metadata={},
            ),
            AlignedThermogram(
                name="t2",
                temp=np.array([100.0, 200.0, 300.0]),
                deltatemp=np.array([1.0, 1.1, 1.2]),
                time=np.array([0.0, 10.0, 20.0]),
                mass=np.array([200.0, 199.0, 198.0]),
                temperature_grid=np.array([100.0, 200.0, 300.0]),
                metadata={},
            ),
        ]
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 200.0, 300.0],
                "deltatemp": [0.1, 0.2, 0.3],
            }),
        )
        result = apply_correction_to_aligned(aligned, correction)
        assert len(result) == 2
        assert np.allclose(result[0].deltatemp, [0.6, 0.8, 1.0])
        assert np.allclose(result[1].deltatemp, [1.1, 1.3, 1.5])

    def test_null_deltatemp(self):
        """Если deltatemp=None, correction становится новым deltatemp."""
        aligned = [AlignedThermogram(
            name="test",
            temp=np.array([100.0, 200.0, 300.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0]),
            mass=np.array([100.0, 99.0, 98.0]),
            temperature_grid=np.array([100.0, 200.0, 300.0]),
            metadata={},
        )]
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 200.0, 300.0],
                "deltatemp": [0.1, 0.2, 0.3],
            }),
        )
        result = apply_correction_to_aligned(aligned, correction)
        assert len(result) == 1
        assert result[0].deltatemp is not None
        assert np.allclose(result[0].deltatemp, [0.1, 0.2, 0.3])

    def test_metadata_updated(self):
        """correction_applied=True в metadata."""
        aligned = [AlignedThermogram(
            name="test",
            temp=np.array([100.0, 200.0, 300.0]),
            deltatemp=np.array([0.5, 0.6, 0.7]),
            time=np.array([0.0, 10.0, 20.0]),
            mass=np.array([100.0, 99.0, 98.0]),
            temperature_grid=np.array([100.0, 200.0, 300.0]),
            metadata={"existing": True},
        )]
        correction = CorrectionFile(
            name="correction",
            frame=pd.DataFrame({
                "temp": [100.0, 200.0, 300.0],
                "deltatemp": [0.1, 0.2, 0.3],
            }),
        )
        result = apply_correction_to_aligned(aligned, correction)
        assert result[0].metadata.get("correction_applied") is True
        assert result[0].metadata.get("existing") is True