from __future__ import annotations

import numpy as np

from tgapp.domain.kinetics.errors import InterpolationError
from tgapp.domain.kinetics.models import (
    IsoconversionalDataset,
    IsoconversionalPoint,
    IsoconversionalRun,
    ConversionSettings,
)


def build_alpha_grid(settings: ConversionSettings) -> np.ndarray:
    """Build a stable alpha grid using linspace.

    Avoids float accumulation error by computing exact point count.
    """
    n_points = round(
        (settings.alpha_max - settings.alpha_min) / settings.alpha_step
    ) + 1
    return np.linspace(settings.alpha_min, settings.alpha_max, int(n_points))


def interpolate_at_alpha(
    alpha: np.ndarray,
    temperature_k: np.ndarray,
    time_s: np.ndarray,
    target_alpha: float,
) -> tuple[float, float]:
    """Interpolate temperature and time at a specific alpha value.

    Uses linear interpolation. Extrapolation is NOT allowed.
    Returns (T, t) or raises InterpolationError if target_alpha is outside range.
    """
    alpha_min = alpha[0]
    alpha_max = alpha[-1]

    if target_alpha < alpha_min - 1e-12 or target_alpha > alpha_max + 1e-12:
        raise InterpolationError(
            f"target_alpha={target_alpha:.4f} outside alpha range "
            f"[{alpha_min:.4f}, {alpha_max:.4f}] — no extrapolation"
        )

    # Clip to valid range for interpolation
    clipped_alpha = np.clip(alpha, alpha_min, alpha_max)

    T = float(np.interp(target_alpha, clipped_alpha, temperature_k))
    t = float(np.interp(target_alpha, clipped_alpha, time_s))

    return T, t


def build_isoconversional_dataset(
    runs: list[IsoconversionalRun],
    alpha_grid: np.ndarray,
) -> IsoconversionalDataset:
    """Build isoconversional dataset from multiple IsoconversionalRun objects.

    For each alpha point on the grid, interpolates T and t from all runs
    that actually cover that alpha value.

    Args:
        runs: list of IsoconversionalRun (must have monotonically increasing alpha)
        alpha_grid: the common alpha grid

    Returns:
        IsoconversionalDataset with points, source run IDs, and warnings
    """
    warnings: list[str] = []
    points: list[IsoconversionalPoint] = []

    for target_alpha in alpha_grid:
        run_ids: list[str] = []
        temperatures: list[float] = []
        heating_rates: list[float] = []
        conv_rates: list[float] = []

        for run in runs:
            # Check if this run covers the target alpha
            if run.alpha[0] <= target_alpha <= run.alpha[-1]:
                try:
                    T, _ = interpolate_at_alpha(
                        run.alpha, run.temperature_k, run.time_s, target_alpha
                    )
                    run_ids.append(run.run_id)
                    temperatures.append(T)
                    heating_rates.append(run.beta_k_s)
                    if run.conversion_rate_s_inv is not None:
                        _, dt = interpolate_at_alpha(
                            run.alpha, run.temperature_k, run.time_s, target_alpha
                        )
                        # Get conversion rate at interpolated time index
                        t_idx = np.searchsorted(run.time_s, dt)
                        if 0 < t_idx < len(run.conversion_rate_s_inv):
                            conv_rates.append(
                                float(run.conversion_rate_s_inv[t_idx])
                            )
                except InterpolationError:
                    # Skip this run for this alpha point
                    pass

        if run_ids:
            point = IsoconversionalPoint(
                alpha=float(target_alpha),
                run_ids=tuple(run_ids),
                temperatures_k=tuple(temperatures),
                heating_rates_k_s=tuple(heating_rates),
                conversion_rates_s_inv=(
                    tuple(conv_rates) if conv_rates else None
                ),
            )
            points.append(point)

    source_run_ids = tuple(sorted(set(r.run_id for r in runs)))

    return IsoconversionalDataset(
        points=tuple(points),
        source_run_ids=source_run_ids,
        warnings=tuple(warnings),
    )