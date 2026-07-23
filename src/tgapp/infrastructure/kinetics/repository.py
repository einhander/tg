"""Versioned kinetic study file repository."""

from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from tgapp.domain.kinetics.models import (
    KineticAnalysisResult,
    KineticStudy,
    KineticRun,
    ConversionSettings,
    HeatingValidationSettings,
)
from tgapp.domain.kinetics.units import TemperatureUnit, TimeUnit, MassUnit


class KineticStudyRepository:
    """File-based versioned repository for kinetic studies."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _study_dir(self, study_id: str) -> Path:
        return self.base_dir / "studies" / study_id

    def _runs_dir(self, study_id: str) -> Path:
        return self._study_dir(study_id) / "runs"

    def _analyses_dir(self, study_id: str) -> Path:
        return self._study_dir(study_id) / "analyses"

    def save_study(self, study: KineticStudy) -> None:
        """Save study manifest and run data."""
        study_dir = self._study_dir(study.study_id)
        runs_dir = self._runs_dir(study.study_id)
        study_dir.mkdir(parents=True, exist_ok=True)
        runs_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "study_id": study.study_id,
            "name": study.name,
            "sample_name": study.sample_name,
            "atmosphere": study.atmosphere,
            "run_ids": [r.run_id for r in study.runs],
            "excluded_run_ids": list(study.excluded_run_ids),
            "conversion_settings": {
                "alpha_min": study.conversion_settings.alpha_min,
                "alpha_max": study.conversion_settings.alpha_max,
                "alpha_step": study.conversion_settings.alpha_step,
                "reaction_temperature_range_k": study.conversion_settings.reaction_temperature_range_k,
                "initial_plateau_range_k": study.conversion_settings.initial_plateau_range_k,
                "final_plateau_range_k": study.conversion_settings.final_plateau_range_k,
                "plateau_statistic": study.conversion_settings.plateau_statistic,
                "minimum_plateau_points": study.conversion_settings.minimum_plateau_points,
                "monotonicity_tolerance": study.conversion_settings.monotonicity_tolerance,
            },
            "validation_settings": {
                "minimum_r_squared": study.validation_settings.minimum_r_squared,
                "maximum_relative_beta_difference": study.validation_settings.maximum_relative_beta_difference,
                "minimum_distinct_beta_ratio": study.validation_settings.minimum_distinct_beta_ratio,
            },
            "version": "1.0",
        }

        (study_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

        # Save each run as npz + json
        for run in study.runs:
            run_dir = runs_dir / run.run_id
            run_dir.mkdir(parents=True, exist_ok=True)

            np.savez(
                run_dir / "data.npz",
                temperature_k=run.temperature_k,
                time_s=run.time_s,
                mass_g=run.mass_g,
            )

            run_meta = {
                "run_id": run.run_id,
                "source_name": run.source_name,
                "source_sha256": run.source_sha256,
                "nominal_heating_rate_k_s": run.nominal_heating_rate_k_s,
                "measured_heating_rate_k_s": run.measured_heating_rate_k_s,
                "heating_linearity_r2": run.heating_linearity_r2,
                "heating_max_residual_k": run.heating_max_residual_k,
                "sample_name": run.sample_name,
                "atmosphere": run.atmosphere,
                "source_temperature_unit": run.source_temperature_unit.value,
                "source_time_unit": run.source_time_unit.value,
                "source_mass_unit": run.source_mass_unit.value,
                "metadata": dict(run.metadata) if hasattr(run.metadata, "items") else run.metadata,
            }
            (run_dir / "metadata.json").write_text(json.dumps(run_meta, indent=2))

    def load_study(self, study_id: str) -> tuple[KineticStudy, dict[str, Any]]:
        """Load study manifest and run metadata.

        Returns (study_config, run_metadata_dict).
        The caller must reconstruct KineticRun objects from the npz files.
        """
        manifest_path = self._study_dir(study_id) / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Study manifest not found: {study_id}")

        manifest = json.loads(manifest_path.read_text())

        # Load run metadata
        runs_dir = self._runs_dir(study_id)
        run_metadatas: dict[str, dict[str, Any]] = {}
        for run_json in runs_dir.glob("*/metadata.json"):
            run_id = run_json.parent.name
            run_metadatas[run_id] = json.loads(run_json.read_text())

        return manifest, run_metadatas

    def load_study_full(self, study_id: str) -> KineticStudy:
        """Load a complete KineticStudy including reconstructed KineticRun objects."""
        manifest_path = self._study_dir(study_id) / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Study manifest not found: {study_id}")

        manifest = json.loads(manifest_path.read_text())

        # Load run metadata
        runs_dir = self._runs_dir(study_id)
        run_metadatas: dict[str, dict[str, Any]] = {}
        for run_json in runs_dir.glob("*/metadata.json"):
            run_id = run_json.parent.name
            run_metadatas[run_id] = json.loads(run_json.read_text())

        # Reconstruct KineticRun objects from npz files
        runs: list[KineticRun] = []
        for run_id in manifest.get("run_ids", []):
            run_dir = runs_dir / run_id
            npz_path = run_dir / "data.npz"
            meta_path = run_dir / "metadata.json"

            if not npz_path.exists() or not meta_path.exists():
                continue

            npz = np.load(str(npz_path))
            meta = json.loads(meta_path.read_text())

            run = KineticRun(
                run_id=run_id,
                source_name=meta["source_name"],
                source_sha256=meta["source_sha256"],
                temperature_k=npz["temperature_k"],
                time_s=npz["time_s"],
                mass_g=npz["mass_g"],
                nominal_heating_rate_k_s=meta.get("nominal_heating_rate_k_s"),
                measured_heating_rate_k_s=meta["measured_heating_rate_k_s"],
                heating_linearity_r2=meta["heating_linearity_r2"],
                heating_max_residual_k=meta["heating_max_residual_k"],
                sample_name=meta.get("sample_name"),
                atmosphere=meta.get("atmosphere"),
                source_temperature_unit=TemperatureUnit(meta["source_temperature_unit"]),
                source_time_unit=TimeUnit(meta["source_time_unit"]),
                source_mass_unit=MassUnit(meta["source_mass_unit"]),
                metadata=meta.get("metadata", {}),
            )
            runs.append(run)

        cs = manifest.get("conversion_settings", {})
        vs = manifest.get("validation_settings", {})

        study = KineticStudy(
            study_id=manifest["study_id"],
            name=manifest["name"],
            runs=tuple(runs),
            excluded_run_ids=frozenset(manifest.get("excluded_run_ids", [])),
            conversion_settings=ConversionSettings(
                alpha_min=cs.get("alpha_min", 0.05),
                alpha_max=cs.get("alpha_max", 0.95),
                alpha_step=cs.get("alpha_step", 0.05),
                reaction_temperature_range_k=cs.get("reaction_temperature_range_k"),
                initial_plateau_range_k=cs.get("initial_plateau_range_k"),
                final_plateau_range_k=cs.get("final_plateau_range_k"),
                plateau_statistic=cs.get("plateau_statistic", "median"),
                minimum_plateau_points=cs.get("minimum_plateau_points", 5),
                monotonicity_tolerance=cs.get("monotonicity_tolerance", 1e-6),
            ),
            validation_settings=HeatingValidationSettings(
                minimum_r_squared=vs.get("minimum_r_squared", 0.995),
                maximum_relative_beta_difference=vs.get("maximum_relative_beta_difference", 0.10),
                minimum_distinct_beta_ratio=vs.get("minimum_distinct_beta_ratio", 1.05),
            ),
            sample_name=manifest.get("sample_name"),
            atmosphere=manifest.get("atmosphere"),
        )

        return study

    def save_analysis(self, result: KineticAnalysisResult) -> Path:
        """Save analysis result as versioned output."""
        analyses_dir = self._analyses_dir(result.study_id)
        analyses_dir.mkdir(parents=True, exist_ok=True)

        analysis_dir = analyses_dir / result.analysis_id
        analysis_dir.mkdir(parents=True, exist_ok=True)

        # Save result JSON
        result_data = {
            "analysis_id": result.analysis_id,
            "study_id": result.study_id,
            "method_id": result.method_id,
            "method_version": result.method_version,
            "mean_activation_energy_j_mol": result.mean_activation_energy_j_mol,
            "median_activation_energy_j_mol": result.median_activation_energy_j_mol,
            "source_run_ids": result.source_run_ids,
            "source_hashes": result.source_hashes,
            "settings": result.settings,
            "warnings": result.warnings,
            "points": [
                {
                    "alpha": p.alpha,
                    "activation_energy_j_mol": p.activation_energy_j_mol,
                    "slope": p.slope,
                    "intercept": p.intercept,
                    "r_squared": p.r_squared,
                    "slope_standard_error": p.slope_standard_error,
                    "run_ids": p.run_ids,
                    "temperatures_k": p.temperatures_k,
                    "heating_rates_k_s": p.heating_rates_k_s,
                    "regression_x": p.regression_x,
                    "regression_y": p.regression_y,
                    "regression_predicted_y": p.regression_predicted_y,
                    "residuals": p.residuals,
                    "status": p.status,
                    "warnings": p.warnings,
                }
                for p in result.points
            ],
        }
        (analysis_dir / "result.json").write_text(json.dumps(result_data, indent=2))

        # Save points CSV
        csv_path = analysis_dir / "points.csv"
        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "alpha",
                    "activation_energy_j_mol",
                    "method_id",
                    "method_version",
                    "slope",
                    "intercept",
                    "r_squared",
                    "slope_standard_error",
                    "run_count",
                    "status",
                    "warnings",
                ]
            )
            for p in result.points:
                writer.writerow(
                    [
                        p.alpha,
                        p.activation_energy_j_mol,
                        result.method_id,
                        result.method_version,
                        p.slope,
                        p.intercept,
                        p.r_squared,
                        p.slope_standard_error,
                        len(p.run_ids),
                        p.status,
                        "; ".join(p.warnings) if p.warnings else "",
                    ]
                )

        return analysis_dir

    def load_analysis(
        self, study_id: str, analysis_id: str
    ) -> dict[str, Any]:
        """Load analysis result JSON."""
        result_path = (
            self._analyses_dir(study_id) / analysis_id / "result.json"
        )
        if not result_path.exists():
            raise FileNotFoundError(f"Analysis result not found: {analysis_id}")
        return json.loads(result_path.read_text())

    def list_analyses(self, study_id: str) -> list[str]:
        """List all analysis IDs for a study."""
        analyses_dir = self._analyses_dir(study_id)
        if not analyses_dir.exists():
            return []
        return [d.name for d in analyses_dir.iterdir() if d.is_dir()]