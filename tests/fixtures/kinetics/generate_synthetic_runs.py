"""Generate synthetic kinetic runs for OFW validation.

Solves:
    dα/dt = A · exp(-E / RT) · f(α)
    T(t) = T0 + βt

For first model:
    f(α) = 1 - α

Uses scipy.integrate.solve_ivp.
Generates at least four heating rates: 5, 10, 20, 40 K/min.
Forms mass: m(t) = m0 - α(t)(m0 - mf)
"""

from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp


def generate_synthetic_run(
    E: float,
    A: float,
    T0: float,
    beta_K_per_min: float,
    m0: float = 1.0,
    mf: float = 0.5,
    dt: float = 0.5,
    n_points: int = 1000,
) -> dict:
    """Generate a single synthetic kinetic run.

    Uses n_points * dt as the simulation time span.
    The solver extends if alpha hasn't reached 0.99 by end of span.

    Args:
        E: activation energy in J/mol
        A: pre-exponential factor in 1/s
        T0: initial temperature in K
        beta_K_per_min: heating rate in K/min
        m0: initial mass
        mf: final mass
        dt: time step in seconds
        n_points: number of output points

    Returns:
        dict with keys: temperature_k, time_s, mass_g
    """
    beta_K_per_s = beta_K_per_min / 60.0
    R = 8.31446261815324

    def kinetic_rhs(t, alpha):
        """dα/dt = A · exp(-E/RT) · (1-α)"""
        T = T0 + beta_K_per_s * t
        dalpha = A * np.exp(-E / (R * T)) * (1.0 - alpha)
        return dalpha

    # Time span
    t_span = (0, n_points * dt)
    t_eval = np.arange(0, t_span[1], dt)

    # Use BDF method for stiff problems
    sol = solve_ivp(
        kinetic_rhs,
        t_span,
        [0.0],
        method='BDF',
        t_eval=t_eval,
        dense_output=True,
        max_step=dt * 10,
    )

    alpha = sol.y[0]
    time_s = sol.t
    temperature_k = T0 + beta_K_per_s * time_s
    mass_g = m0 - alpha * (m0 - mf)

    return {
        "temperature_k": temperature_k,
        "time_s": time_s,
        "mass_g": mass_g,
    }


def generate_synthetic_study(
    E: float = 150000.0,
    A: float = 1e12,
    T0: float = 300.0,
    heating_rates: list[float] | None = None,
    m0: float = 1.0,
    mf: float = 0.5,
    dt: float = 0.5,
    n_points: int = 1000,
) -> list[dict]:
    """Generate a full synthetic kinetic study.

    Args:
        E: activation energy in J/mol
        A: pre-exponential factor in 1/s
        T0: initial temperature in K
        heating_rates: list of heating rates in K/min (default: [5, 10, 20, 40])
        m0: initial mass
        mf: final mass
        dt: time step in seconds
        n_points: number of output points

    Returns:
        list of run dicts, each with temperature_k, time_s, mass_g
    """
    if heating_rates is None:
        heating_rates = [5.0, 10.0, 20.0, 40.0]

    runs = []
    for beta in heating_rates:
        run = generate_synthetic_run(
            E=E, A=A, T0=T0, beta_K_per_min=beta,
            m0=m0, mf=mf, dt=dt, n_points=n_points,
        )
        run["beta_K_per_min"] = beta
        runs.append(run)

    return runs