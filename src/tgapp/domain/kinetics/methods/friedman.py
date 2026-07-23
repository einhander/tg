"""Friedman differential method."""

from __future__ import annotations

import numpy as np
import uuid

from tgapp.domain.kinetics.constants import GAS_CONSTANT_J_MOL_K
from tgapp.domain.kinetics.errors import (
    RegressionError,
)
from tgapp.domain.kinetics.methods.base import BaseKineticMethod
from tgapp.domain.kinetics.models import (
    IsoconversionalDataset,
    IsoconversionalRun,
    KineticAnalysisResult,
    KineticPointResult,
    LinearRegressionResult,
)


class FriedmanMethod(BaseKineticMethod):
    """Friedman differential method.

    Mathematical form:
        ln(dα/dt) = Cα − Eα / (R · Tα)

    At:
        x = 1 / Tα
        y = ln(dα/dt)

    Energy:
        Eα = −slope · R

    Note: Friedman is a differential method, sensitive to noise in dα/dt.
    Conversion rates must be pre-computed and smoothed before use.
    """

    method_id = "friedman"
    display_name = "Friedman"
    method_version = "1.0"

    def analyze(
        self,
        dataset: IsoconversionalDataset,
    ) -> KineticAnalysisResult:
        """Perform Friedman analysis on the isoconversional dataset.

        Requires conversion_rate_s_inv to be populated in IsoconversionalRun.
        """
        points: list[KineticPointResult] = []
        all_warnings: list[str] = []

        for point in dataset.points:
            run_ids = point.run_ids
            temperatures = point.temperatures_k
            heating_rates = point.heating_rates_k_s
            conv_rates = point.conversion_rates_s_inv

            if len(run_ids) < 3:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None, intercept=None, r_squared=None, slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=(), regression_y=(), regression_predicted_y=(), residuals=(),
                    status="insufficient_runs",
                    warnings=(f"Only {len(run_ids)} run(s) available, minimum 3 required",),
                ))
                continue

            # Friedman requires conversion rates
            if conv_rates is None or all(cr is None for cr in conv_rates):
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None, intercept=None, r_squared=None, slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=(), regression_y=(), regression_predicted_y=(), residuals=(),
                    status="no_conversion_rates",
                    warnings=("dα/dt not available — Friedman requires pre-computed conversion rates",),
                ))
                continue

            # Filter out non-positive conversion rates (cannot take ln)
            valid_mask = [cr is not None and cr > 0 for cr in conv_rates]
            if sum(valid_mask) < 3:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None, intercept=None, r_squared=None, slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=(), regression_y=(), regression_predicted_y=(), residuals=(),
                    status="insufficient_valid_rates",
                    warnings=("Fewer than 3 positive conversion rates after filtering",),
                ))
                all_warnings.append(f"Alpha={point.alpha:.4f}: insufficient valid dα/dt values")
                continue

            # Apply mask
            valid_run_ids = tuple(run_ids[i] for i in range(len(run_ids)) if valid_mask[i])
            valid_temps = tuple(temperatures[i] for i in range(len(temperatures)) if valid_mask[i])
            valid_conv_rates = tuple(conv_rates[i] for i in range(len(conv_rates)) if valid_mask[i])

            # Friedman: y = ln(dα/dt), x = 1/T
            x = np.array([1.0 / T for T in valid_temps], dtype=np.float64)
            y = np.array([np.log(cr) for cr in valid_conv_rates], dtype=np.float64)

            try:
                reg = self._run_regression(x, y)
            except RegressionError as e:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None, intercept=None, r_squared=None, slope_standard_error=None,
                    run_ids=valid_run_ids,
                    temperatures_k=valid_temps,
                    heating_rates_k_s=tuple(heating_rates[i] for i in range(len(heating_rates)) if valid_mask[i]),
                    regression_x=tuple(float(xi) for xi in x),
                    regression_y=tuple(float(yi) for yi in y),
                    regression_predicted_y=(), residuals=(),
                    status="regression_error",
                    warnings=(str(e),),
                ))
                continue

            slope = reg.slope
            activation_energy_j_mol = -slope * GAS_CONSTANT_J_MOL_K

            point_warnings: list[str] = []
            if activation_energy_j_mol < 0:
                point_warnings.append("Negative activation energy — check data quality")
                status = "negative_energy"
            elif reg.r_squared < 0.95:
                point_warnings.append(f"Low R²={reg.r_squared:.4f} — questionable fit")
                status = "questionable"
            else:
                status = "valid"

            point_warnings.extend(dataset.warnings)

            points.append(KineticPointResult(
                alpha=point.alpha,
                activation_energy_j_mol=activation_energy_j_mol,
                slope=slope,
                intercept=reg.intercept,
                r_squared=reg.r_squared,
                slope_standard_error=reg.slope_standard_error,
                run_ids=valid_run_ids,
                temperatures_k=valid_temps,
                heating_rates_k_s=tuple(heating_rates[i] for i in range(len(heating_rates)) if valid_mask[i]),
                regression_x=tuple(float(xi) for xi in x),
                regression_y=tuple(float(yi) for yi in y),
                regression_predicted_y=reg.predicted,
                residuals=reg.residuals,
                status=status,
                warnings=tuple(point_warnings),
            ))

        valid_energies = [
            p.activation_energy_j_mol
            for p in points
            if p.activation_energy_j_mol is not None and p.status == "valid"
        ]

        mean_e: float | None = None
        median_e: float | None = None
        if valid_energies:
            arr = np.array(valid_energies)
            mean_e = float(np.mean(arr))
            median_e = float(np.median(arr))

        return KineticAnalysisResult(
            analysis_id=str(uuid.uuid4()),
            study_id="",
            method_id=self.method_id,
            method_version=self.method_version,
            points=tuple(points),
            mean_activation_energy_j_mol=mean_e,
            median_activation_energy_j_mol=median_e,
            source_run_ids=dataset.source_run_ids,
            source_hashes=dataset.source_run_ids,
            settings={},
            warnings=tuple(all_warnings),
        )

    def _run_regression(self, x: np.ndarray, y: np.ndarray) -> LinearRegressionResult:
        from tgapp.domain.kinetics.regression import linear_regression as lr
        return lr(x, y)