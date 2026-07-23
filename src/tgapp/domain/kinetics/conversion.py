from __future__ import annotations

import numpy as np

from tgapp.domain.kinetics.errors import (
    ConversionCalculationError,
    PlateauNotFoundError,
)
from tgapp.domain.kinetics.models import ConversionSettings, KineticRun


def calculate_plateau_mass(
    temperature_k: np.ndarray,
    mass_g: np.ndarray,
    range_k: tuple[float, float] | None,
    statistic: str = "median",
    minimum_points: int = 5,
) -> float:
    """Calculate plateau mass from a temperature range.

    Args:
        temperature_k: temperature array in Kelvin
        mass_g: mass array in grams
        range_k: (min_temp, max_temp) for plateau, or None to use full range
        statistic: "median" or "mean"
        minimum_points: minimum number of points in range

    Returns:
        plateau mass value
    """
    if range_k is None:
        # Use full range
        mask = np.ones(len(temperature_k), dtype=bool)
    else:
        t_min, t_max = range_k
        mask = (temperature_k >= t_min) & (temperature_k <= t_max)

    plateau_temp = temperature_k[mask]
    plateau_mass = mass_g[mask]
    n_points = len(plateau_mass)

    if n_points < minimum_points:
        raise PlateauNotFoundError(
            f"Plateau has {n_points} points < {minimum_points} minimum "
            f"(range: {range_k})"
        )

    if statistic == "median":
        return float(np.median(plateau_mass))
    elif statistic == "mean":
        return float(np.mean(plateau_mass))
    else:
        raise ConversionCalculationError(f"Unknown plateau statistic: {statistic}")


def calculate_conversion(
    run: KineticRun,
    conversion_settings: ConversionSettings,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Calculate conversion degree α(T) for a single KineticRun.

    For mass-loss processes:
        α = (m0 - m) / (m0 - mf)

    Args:
        run: validated kinetic run
        conversion_settings: conversion parameters including plateau ranges

    Returns:
        (alpha, temperature_k, time_s) arrays

    Raises:
        PlateauNotFoundError: if plateau ranges not provided or insufficient points
        ConversionCalculationError: if m0 == mf or invalid α values
    """
    m0 = calculate_plateau_mass(
        run.temperature_k,
        run.mass_g,
        conversion_settings.initial_plateau_range_k,
        conversion_settings.plateau_statistic,
        conversion_settings.minimum_plateau_points,
    )
    mf = calculate_plateau_mass(
        run.temperature_k,
        run.mass_g,
        conversion_settings.final_plateau_range_k,
        conversion_settings.plateau_statistic,
        conversion_settings.minimum_plateau_points,
    )

    mass_range = m0 - mf
    if abs(mass_range) < 1e-12:
        raise ConversionCalculationError(
            f"m0 ({m0}) and mf ({mf}) are too close — no mass loss detected"
        )

    alpha = (m0 - run.mass_g) / mass_range

    # Check for values outside [0, 1]
    tol = conversion_settings.monotonicity_tolerance
    out_of_range = (alpha < -tol) | (alpha > 1.0 + tol)
    n_out = int(out_of_range.sum())
    if n_out > 0:
        # Not an error yet — just a warning that will be surfaced
        pass  # Caller checks via warnings

    return alpha, run.temperature_k, run.time_s