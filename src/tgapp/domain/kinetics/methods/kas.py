"""Kissinger–Akahira–Sunose (KAS) method."""

from __future__ import annotations

import numpy as np
import uuid

from tgapp.domain.kinetics.constants import GAS_CONSTANT_J_MOL_K
from tgapp.domain.kinetics.errors import (
    InsufficientRunsError,
    IdenticalHeatingRatesError,
    RegressionError,
)
from tgapp.domain.kinetics.methods.base import BaseKineticMethod
from tgapp.domain.kinetics.models import (
    IsoconversionalDataset,
    KineticAnalysisResult,
    KineticPointResult,
    LinearRegressionResult,
)


class KissingerAkahiraSunoseMethod(BaseKineticMethod):
    """Kissinger–Akahira–Sunose method.

    Mathematical form:
        ln(β / Tα²) = Cα − Eα / (R · Tα)

    At:
        x = 1 / Tα
        y = ln(β / Tα²)

    Energy:
        Eα = −slope · R
    """

    method_id = "kas"
    display_name = "Kissinger–Akahira–Sunose"
    method_version = "1.0"

    def analyze(
        self,
        dataset: IsoconversionalDataset,
    ) -> KineticAnalysisResult:
        """Perform KAS analysis on the isoconversional dataset."""
        points: list[KineticPointResult] = []
        all_warnings: list[str] = []

        for point in dataset.points:
            run_ids = point.run_ids
            temperatures = point.temperatures_k
            heating_rates = point.heating_rates_k_s

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

            unique_rates = set(round(r, 6) for r in heating_rates)
            if len(unique_rates) < 2:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None, intercept=None, r_squared=None, slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=(), regression_y=(), regression_predicted_y=(), residuals=(),
                    status="identical_heating_rates",
                    warnings=("All heating rates are identical",),
                ))
                all_warnings.append(f"Alpha={point.alpha:.4f}: identical heating rates")
                continue

            # KAS: y = ln(β / T²), x = 1/T
            x = np.array([1.0 / T for T in temperatures], dtype=np.float64)
            y = np.array([np.log(beta / (T ** 2)) for beta, T in zip(heating_rates, temperatures)], dtype=np.float64)

            try:
                reg = self._run_regression(x, y)
            except RegressionError as e:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None, intercept=None, r_squared=None, slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=tuple(float(xi) for xi in x),
                    regression_y=tuple(float(yi) for yi in y),
                    regression_predicted_y=(), residuals=(),
                    status="regression_error",
                    warnings=(str(e),),
                ))
                continue

            # Eα = −slope · R
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
                run_ids=run_ids,
                temperatures_k=temperatures,
                heating_rates_k_s=heating_rates,
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