from __future__ import annotations

import numpy as np
import pytest

from tgapp.domain.alignment import align_thermograms
from tgapp.domain.models import (
    AlignedThermogram,
    NoCommonRangeError,
    ValidatedThermogram,
)


class TestAlignThermograms:
    def test_single_thermogram(self):
        v = ValidatedThermogram(
            name="test",
            temp=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0, 30.0, 40.0]),
            mass=np.array([100.0, 99.0, 97.0, 94.0, 90.0]),
            metadata={},
        )
        aligned = align_thermograms([v], bins=5)
        assert len(aligned) == 1
        assert aligned[0].name == "test"
        assert len(aligned[0].temperature_grid) == 5
        assert np.allclose(aligned[0].temperature_grid, v.temp)

    def test_two_thermograms_common_range(self):
        v1 = ValidatedThermogram(
            name="t1",
            temp=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0, 30.0, 40.0]),
            mass=np.array([100.0, 99.0, 97.0, 94.0, 90.0]),
            metadata={},
        )
        v2 = ValidatedThermogram(
            name="t2",
            temp=np.array([150.0, 250.0, 350.0, 450.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0, 30.0]),
            mass=np.array([200.0, 195.0, 188.0, 175.0]),
            metadata={},
        )
        aligned = align_thermograms([v1, v2], bins=5)
        assert len(aligned) == 2
        assert aligned[0].name == "t1"
        assert aligned[1].name == "t2"
        assert len(aligned[0].temperature_grid) == 5
        # common range [150, 450], linspace(150, 450, 5) = [150, 225, 300, 375, 450]
        assert np.allclose(aligned[0].temperature_grid, [150.0, 225.0, 300.0, 375.0, 450.0])

    def test_no_common_range_raises(self):
        v1 = ValidatedThermogram(
            name="t1",
            temp=np.array([100.0, 200.0, 300.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0]),
            mass=np.array([100.0, 99.0, 98.0]),
            metadata={},
        )
        v2 = ValidatedThermogram(
            name="t2",
            temp=np.array([400.0, 500.0, 600.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0]),
            mass=np.array([200.0, 199.0, 198.0]),
            metadata={},
        )
        with pytest.raises(NoCommonRangeError):
            align_thermograms([v1, v2])

    def test_empty_list(self):
        assert align_thermograms([]) == []

    def test_with_deltatemp(self):
        v = ValidatedThermogram(
            name="test",
            temp=np.array([100.0, 200.0, 300.0, 400.0, 500.0]),
            deltatemp=np.array([0.1, 0.2, 0.3, 0.4, 0.5]),
            time=np.array([0.0, 10.0, 20.0, 30.0, 40.0]),
            mass=np.array([100.0, 99.0, 97.0, 94.0, 90.0]),
            metadata={},
        )
        aligned = align_thermograms([v], bins=5)
        assert aligned[0].deltatemp is not None
        assert len(aligned[0].deltatemp) == 5

    def test_mass_interpolation(self):
        v = ValidatedThermogram(
            name="t1",
            temp=np.array([100.0, 300.0, 500.0]),
            deltatemp=None,
            time=np.array([0.0, 10.0, 20.0]),
            mass=np.array([100.0, 95.0, 90.0]),
            metadata={},
        )
        aligned = align_thermograms([v], bins=3)
        assert np.allclose(aligned[0].mass, [100.0, 95.0, 90.0])