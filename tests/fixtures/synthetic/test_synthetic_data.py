"""Synthetic data generators and their own self-tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tgapp.domain.summary import build_heat_speed_text


def make_linear_temp_time(n: int = 100, T0: float = 25.0, beta: float = 10.0) -> pd.DataFrame:
    """T(t) = T0 + beta*t → DataFrame columns: temp, time, deltatemp, mass."""
    t = np.linspace(0.0, 100.0, num=n)
    T = T0 + beta * t
    return pd.DataFrame({
        "temp": T,
        "time": t,
        "deltatemp": 0.0,
        "mass": 100.0,
    })


def make_constant_mass(n: int = 100, m0: float = 100.0) -> pd.DataFrame:
    """Constant mass m0, linearly increasing temp."""
    t = np.linspace(0.0, 100.0, num=n)
    return pd.DataFrame({
        "temp": 25.0 + 10.0 * t,
        "time": t,
        "deltatemp": 0.0,
        "mass": m0,
    })


def make_linear_mass_loss(n: int = 100, m0: float = 100.0, rate: float = 0.5) -> pd.DataFrame:
    """Linear mass loss: m(t) = m0 - rate*t."""
    t = np.linspace(0.0, 100.0, num=n)
    return pd.DataFrame({
        "temp": 25.0 + 10.0 * t,
        "time": t,
        "deltatemp": 0.0,
        "mass": m0 - rate * t,
    })


# ---------------------------------------------------------------------------
# Self-tests
# ---------------------------------------------------------------------------


def test_make_linear_temp_time_heat_speed():
    """T0=0 → speed = beta exactly."""
    df3 = make_linear_temp_time(n=50, T0=0.0, beta=10.0)
    text3 = build_heat_speed_text(df3)
    assert "10.0" in text3


def test_make_linear_mass_loss_derivative():
    """np.gradient(mass, time) ≈ -rate."""
    df = make_linear_mass_loss(n=100, m0=100.0, rate=0.5)
    mass = df["mass"].to_numpy(dtype=float)
    time = df["time"].to_numpy(dtype=float)
    dmdt_approx = np.gradient(mass, time)
    assert np.allclose(dmdt_approx, -0.5, atol=0.01)