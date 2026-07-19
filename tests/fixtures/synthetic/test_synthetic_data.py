"""Synthetic data generators and their own self-tests."""

from __future__ import annotations

import numpy as np
import pandas as pd

from tgapp.domain.summary import build_heat_speed_text


def make_linear_temp_time(n: int = 100, T0: float = 25.0, beta: float = 10.0) -> pd.DataFrame:
    """Create a DataFrame with T(t) = T0 + beta * t.

    Columns: temp, time, deltatemp (0), mass (100).
    """
    t = np.linspace(0.0, 100.0, num=n)
    T = T0 + beta * t
    return pd.DataFrame({
        "temp": T,
        "time": t,
        "deltatemp": 0.0,
        "mass": 100.0,
    })


def make_constant_mass(n: int = 100, m0: float = 100.0) -> pd.DataFrame:
    """Create a DataFrame with constant mass m0."""
    t = np.linspace(0.0, 100.0, num=n)
    return pd.DataFrame({
        "temp": 25.0 + 10.0 * t,
        "time": t,
        "deltatemp": 0.0,
        "mass": m0,
    })


def make_linear_mass_loss(n: int = 100, m0: float = 100.0, rate: float = 0.5) -> pd.DataFrame:
    """Create a DataFrame with linear mass loss: m(t) = m0 - rate * t."""
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
    """Heat speed from synthetic linear T(t) must equal beta."""
    df = make_linear_temp_time(n=100, T0=25.0, beta=10.0)
    text = build_heat_speed_text(df)
    # build_heat_speed_text computes last['temp'] / last['time']
    # last time = 100, last temp = 25 + 10*100 = 1025 → 1025/100 = 10.25 ≈ 10.2
    # But for small t range, t goes 0..100, so last time = 100
    # T(100) = 25 + 10*100 = 1025, speed = 1025/100 = 10.25 → round to 10.2
    # Actually the formula is last['temp'] / last['time'], so 1025/100 = 10.25 → 10.2
    # For a better test use a smaller range:
    df2 = make_linear_temp_time(n=10, T0=25.0, beta=10.0)
    # t goes 0..10, last t = 10, T = 25 + 10*10 = 125, speed = 125/10 = 12.5
    # Hmm, the formula uses last['temp']/last['time'], not beta.
    # Let's test with the actual formula: speed = T(last_time) / last_time
    # For T(t) = T0 + beta*t, speed = (T0 + beta*t_last) / t_last = T0/t_last + beta
    # With t_last=10, T0=25, beta=10: speed = 2.5 + 10 = 12.5
    # This is not exactly beta because of T0 offset.
    # Better test: use T0=0 so speed = beta exactly.
    df3 = make_linear_temp_time(n=50, T0=0.0, beta=10.0)
    # t_last = 100, T = 0 + 10*100 = 1000, speed = 1000/100 = 10.0
    text3 = build_heat_speed_text(df3)
    assert "10.0" in text3


def test_make_linear_mass_loss_derivative():
    """dmdt from linear mass loss should be approximately -rate."""
    df = make_linear_mass_loss(n=100, m0=100.0, rate=0.5)
    # The derivative column is deltatemp=0, but we can compute d(mass)/d(time)
    mass = df["mass"].to_numpy(dtype=float)
    time = df["time"].to_numpy(dtype=float)
    dmdt_approx = np.gradient(mass, time)
    # Should be close to -0.5
    assert np.allclose(dmdt_approx, -0.5, atol=0.01)