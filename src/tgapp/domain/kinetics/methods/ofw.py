from __future__ import annotations

import numpy as np
import uuid

from tgapp.domain.kinetics.constants import GAS_CONSTANT_J_MOL_K, OFW_DOYLE_SLOPE_FACTOR
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


class OzawaFlynnWallMethod(BaseKineticMethod):
    """Ozawa–Flynn–Wall method using Doyle approximation.

    Mathematical form:
        log10(β) = Cα − 0.4567 · Eα / (R · Tα)

    At:
        x = 1 / Tα
        y = log10(β)

    Energy:
        Eα = −slope · R / 0.4567
    """

    method_id = "ofw_doyle"
    display_name = "Ozawa–Flynn–Wall"
    method_version = "1.0"

    def analyze(
        self,
        dataset: IsoconversionalDataset,
    ) -> KineticAnalysisResult:
        """Perform OFW analysis on the isoconversional dataset.

        For each alpha point:
        1. Get Tα and β for available runs
        2. Check minimum 3 runs
        3. Calculate x = 1/T, y = log10(β)
        4. Run linear regression
        5. Calculate Eα = −slope · R / 0.4567
        6. Save diagnostics
        7. Mark point as questionable at low R²
        8. Do NOT remove runs automatically
        """
        points: list[KineticPointResult] = []
        all_warnings: list[str] = []

        for point in dataset.points:
            run_ids = point.run_ids
            temperatures = point.temperatures_k
            heating_rates = point.heating_rates_k_s

            # Check minimum 3 runs
            if len(run_ids) < 3:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None,
                    intercept=None,
                    r_squared=None,
                    slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=(),
                    regression_y=(),
                    regression_predicted_y=(),
                    residuals=(),
                    status="insufficient_runs",
                    warnings=(f"Only {len(run_ids)} run(s) available, minimum 3 required",),
                ))
                continue

            # Check for identical heating rates
            unique_rates = set(round(r, 6) for r in heating_rates)
            if len(unique_rates) < 2:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None,
                    intercept=None,
                    r_squared=None,
                    slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=(),
                    regression_y=(),
                    regression_predicted_y=(),
                    residuals=(),
                    status="identical_heating_rates",
                    warnings=("All heating rates are identical",),
                ))
                all_warnings.append(f"Alpha={point.alpha:.4f}: identical heating rates")
                continue

            # OFW calculation
            x = np.array([1.0 / T for T in temperatures], dtype=np.float64)
            y = np.array([np.log10(beta) for beta in heating_rates], dtype=np.float64)

            try:
                reg = self._run_regression(x, y)
            except RegressionError as e:
                points.append(KineticPointResult(
                    alpha=point.alpha,
                    activation_energy_j_mol=None,
                    slope=None,
                    intercept=None,
                    r_squared=None,
                    slope_standard_error=None,
                    run_ids=run_ids,
                    temperatures_k=temperatures,
                    heating_rates_k_s=heating_rates,
                    regression_x=tuple(float(xi) for xi in x),
                    regression_y=tuple(float(yi) for yi in y),
                    regression_predicted_y=(),
                    residuals=(),
                    status="regression_error",
                    warnings=(str(e),),
                ))
                continue

            # Eα = −slope · R / 0.4567
            slope = reg.slope
            activation_energy_j_mol = -slope * GAS_CONSTANT_J_MOL_K / OFW_DOYLE_SLOPE_FACTOR

            # Sanity check: energy should be positive
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

        # Calculate summary statistics
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

        source_run_ids = dataset.source_run_ids
        source_hashes = tuple(r for r in dataset.source_run_ids)  # placeholder — actual hashes from study manifest

        return KineticAnalysisResult(
            analysis_id=str(uuid.uuid4()),
            study_id="",  # set by application layer
            method_id=self.method_id,
            method_version=self.method_version,
            points=tuple(points),
            mean_activation_energy_j_mol=mean_e,
            median_activation_energy_j_mol=median_e,
            source_run_ids=source_run_ids,
            source_hashes=source_hashes,
            settings={},  # set by application layer
            warnings=tuple(all_warnings),
        )

    def _run_regression(self, x: np.ndarray, y: np.ndarray) -> LinearRegressionResult:
        """Run linear regression with proper error handling."""
        from tgapp.domain.kinetics.regression import linear_regression as lr

        return lr(x, y)