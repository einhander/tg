"""Unified processing engine — PLAN_AUDIT §14.

Pipeline:
  parse → validate → normalize units → determine common physical range
  → align each experiment → smooth each experiment → calculate derivatives
  → apply correction → aggregate traces → detect peaks → calculate summary
  → return immutable ProcessingResult
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from typing import Any

import numpy as np
import pandas as pd

from tgapp.domain.alignment import align_thermograms
from tgapp.domain.correction import apply_correction_to_aligned
from tgapp.domain.models import (
    AlignedThermogram,
    CorrectionFile,
    PeakResult,
    ProcessingSettings,
    SummaryResult,
    ValidatedThermogram,
)
from tgapp.domain.peaks import detect_peaks
from tgapp.domain.smoothing import (
    smooth_column_savitzky_golay,
    smooth_derivative,
    smooth_derivative_savitzky_golay,
    smooth_mass,
    smooth_temperature,
    smooth_temperature_savitzky_golay,
)
from tgapp.domain.summary import build_heat_speed_text, build_summary
from tgapp.domain.validator import validate_parsed

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ProcessingResult:
    """Immutable result of the processing pipeline."""

    combined: str  # comma-separated file names
    mass_smoothed: pd.DataFrame  # temp, mass
    temp_smoothed: pd.DataFrame  # time, temp, deltatemp
    derivatives: pd.DataFrame  # all columns (temp, mass, time, deltatemp, dmdt)
    peaks: list[PeakResult]
    summary: SummaryResult
    heat_speed_text: str
    metadata: dict = field(default_factory=dict)

    @property
    def mean_frame(self) -> pd.DataFrame:
        """Legacy accessor — returns derivatives (full frame)."""
        return self.derivatives


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ProcessingEngine:
    """Single unified processing pipeline.

    Input: list[ValidatedThermogram] + ProcessingSettings + optional CorrectionFile
    Output: ProcessingResult (frozen dataclass)
    """

    def __init__(self, settings: ProcessingSettings | None = None):
        self.settings = settings or ProcessingSettings()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process(
        self,
        validated: list[ValidatedThermogram],
        settings: ProcessingSettings | None = None,
        correction: CorrectionFile | None = None,
    ) -> ProcessingResult:
        """Run the full processing pipeline.

        Args:
            validated: list of validated thermograms (post-parsing validation)
            settings: processing parameters (overrides self.settings)
            correction: optional temperature correction file

        Returns:
            ProcessingResult with immutable views of all intermediate data.
        """
        effective_settings = settings or self.settings

        # 1. Defensive re-validation
        re_validated = self._re_validate(validated)
        if not re_validated:
            return self._empty_result([])

        # 2. Determine common physical range & align
        aligned = self._align(re_validated, effective_settings.bins)

        # 3. Apply temperature correction (if enabled)
        corrected = self._apply_correction(aligned, correction, effective_settings.use_correction)

        # 4. Smooth each experiment individually
        smoothed = self._smooth_each(corrected, effective_settings)

        # 5. Calculate dm/dt for each experiment
        dmdt_traces = [self._compute_dmdt(frame) for frame in smoothed]

        # 6. Aggregate traces (mean)
        mean_frame = self._aggregate_traces(smoothed, dmdt_traces, effective_settings)

        # 7. Apply correction to mean frame's deltatemp (inline correction for legacy compat)
        if effective_settings.use_correction and correction is not None:
            mean_frame = self._apply_inline_correction(mean_frame, correction, effective_settings.bins)

        # 8. Post-aggregation smoothing
        mean_frame = self._smooth_mean(mean_frame, effective_settings)

        # 9. Detect peaks on unrounded data
        peaks = detect_peaks(mean_frame, effective_settings)

        # 10. Round for output
        mean_frame = self._round_frame(mean_frame)

        # 11. Build summary & heat speed
        file_names = [v.name for v in re_validated]
        summary = build_summary(
            # Build minimal ThermogramFile stubs for summary
            [type("Stub", (), {"name": n})() for n in file_names],
            mean_frame,
            peaks,
        )
        heat_speed = build_heat_speed_text(mean_frame)

        # 12. Assemble immutable result
        return ProcessingResult(
            combined=", ".join(file_names),
            mass_smoothed=mean_frame.loc[
                :, [c for c in ("temp", "mass") if c in mean_frame.columns]
            ].copy(),
            temp_smoothed=mean_frame.loc[
                :, [c for c in ("time", "temp", "deltatemp") if c in mean_frame.columns]
            ].copy(),
            derivatives=mean_frame.copy(),
            peaks=peaks,
            summary=summary,
            heat_speed_text=heat_speed,
            metadata={
                "correction_applied": effective_settings.use_correction and correction is not None,
                "settings": asdict(effective_settings),
                "thermogram_count": len(re_validated),
            },
        )

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    @staticmethod
    def _re_validate(validated: list[ValidatedThermogram]) -> list[ValidatedThermogram]:
        """Defensive re-validation of already-validated thermograms."""
        result: list[ValidatedThermogram] = []
        for v in validated:
            try:
                rv = validate_parsed(v.temp, v.deltatemp, v.time, v.mass)
                result.append(ValidatedThermogram(
                    name=v.name,
                    temp=rv.temp,
                    deltatemp=rv.deltatemp,
                    time=rv.time,
                    mass=rv.mass,
                    metadata=rv.metadata,
                ))
            except Exception as exc:
                logger.warning("Re-validation failed for %s: %s", v.name, exc)
        return result

    @staticmethod
    def _align(
        validated: list[ValidatedThermogram],
        bins: int,
    ) -> list[AlignedThermogram]:
        """Align thermograms on common temperature grid."""
        return align_thermograms(validated, bins=bins)

    @staticmethod
    def _apply_correction(
        aligned: list[AlignedThermogram],
        correction: CorrectionFile | None,
        use_correction: bool,
    ) -> list[AlignedThermogram]:
        """Apply temperature correction to aligned thermograms."""
        if not use_correction or correction is None:
            return aligned
        try:
            return apply_correction_to_aligned(aligned, correction)
        except Exception as exc:
            logger.warning("Correction skipped: %s", exc)
            return aligned

    @staticmethod
    def _smooth_each(
        aligned: list[AlignedThermogram],
        settings: ProcessingSettings,
    ) -> list[pd.DataFrame]:
        """Smooth each experiment individually before derivative computation."""
        smoothed: list[pd.DataFrame] = []
        for a in aligned:
            frame = pd.DataFrame({
                "temp": a.temp,
                "time": a.time,
                "mass": a.mass,
            })
            if a.deltatemp is not None:
                frame["deltatemp"] = a.deltatemp

            if settings.sg_mode:
                smoothed.append(
                    smooth_column_savitzky_golay(
                        frame, "mass", settings.sg_window, settings.sg_polyorder,
                    )
                )
            else:
                smoothed.append(smooth_mass(frame, settings.mass_smoothing))
        return smoothed

    @staticmethod
    def _compute_dmdt(frame: pd.DataFrame) -> pd.Series:
        """Calculate dm/dt for one experiment via np.gradient."""
        if frame.empty or "mass" not in frame.columns or "time" not in frame.columns:
            return pd.Series([np.nan] * 500, name="dmdt", dtype="float64")

        mass = frame["mass"].to_numpy(dtype=float)
        time = frame["time"].to_numpy(dtype=float)
        dmdt = np.gradient(mass, time)
        return pd.Series(dmdt, name="dmdt", dtype="float64", index=frame.index)

    @staticmethod
    def _aggregate_traces(
        smoothed: list[pd.DataFrame],
        dmdt_traces: list[pd.Series],
        settings: ProcessingSettings,
    ) -> pd.DataFrame:
        """Average traces and derivatives on common grid."""
        if not smoothed:
            return pd.DataFrame()

        # Stack mass, temp, time, deltatemp and average
        columns_to_stack = ["temp", "time", "mass"]
        if "deltatemp" in smoothed[0].columns:
            columns_to_stack.append("deltatemp")

        stacked = np.stack([
            frame.loc[:, columns_to_stack].to_numpy(dtype=float)
            for frame in smoothed
        ], axis=0)
        means = stacked.mean(axis=0)
        mean_frame = pd.DataFrame(means, columns=columns_to_stack)

        # Average dmdt
        if dmdt_traces:
            mean_dmdt = ProcessingEngine._average_dmdt(dmdt_traces)
            mean_frame["dmdt"] = mean_dmdt

        return mean_frame

    @staticmethod
    def _average_dmdt(traces: list[pd.Series]) -> pd.Series:
        """Average dm/dt traces, handling length mismatches."""
        if not traces:
            return pd.Series([np.nan] * 500, name="dmdt", dtype="float64")

        lengths = {len(t) for t in traces}
        if len(lengths) == 1:
            stacked = np.stack([t.to_numpy(dtype=float) for t in traces], axis=0)
            return pd.Series(np.nanmean(stacked, axis=0), name="dmdt", dtype="float64")

        # Interpolate to longest
        max_len = max(len(t) for t in traces)
        aligned = []
        for t in traces:
            if len(t) == max_len:
                aligned.append(t)
            else:
                old_idx = np.linspace(0, max_len - 1, len(t))
                new_idx = np.linspace(0, max_len - 1, max_len)
                aligned.append(pd.Series(
                    np.interp(new_idx, old_idx, t.to_numpy(dtype=float)),
                    name="dmdt",
                    dtype="float64",
                ))
        stacked = np.stack([t.to_numpy(dtype=float) for t in aligned], axis=0)
        return pd.Series(np.nanmean(stacked, axis=0), name="dmdt", dtype="float64")

    @staticmethod
    def _apply_inline_correction(
        frame: pd.DataFrame,
        correction: CorrectionFile,
        bins: int,
    ) -> pd.DataFrame:
        """Apply correction to mean frame's deltatemp (legacy compat path)."""
        if frame.empty or "deltatemp" not in frame.columns:
            return frame

        # Resample correction to match frame length
        corr_frame = correction.frame.copy()
        corr_frame["temp"] = pd.to_numeric(corr_frame["temp"], errors="coerce")
        corr_frame["deltatemp"] = pd.to_numeric(corr_frame["deltatemp"], errors="coerce")
        valid = corr_frame.dropna(subset=["temp", "deltatemp"])
        if len(valid) < 2:
            return frame

        # Simple interpolation on the correction's temp axis
        corr_temp = valid["temp"].to_numpy(dtype=float)
        corr_deltatemp = valid["deltatemp"].to_numpy(dtype=float)

        # Interpolate correction onto the mean frame's temperature grid
        if "temp" in frame.columns:
            mean_temp = frame["temp"].to_numpy(dtype=float)
            correction_values = np.interp(mean_temp, corr_temp, corr_deltatemp)
            result = frame.copy()
            result["deltatemp"] = result["deltatemp"].to_numpy(dtype=float) + correction_values
            return result

        return frame

    @staticmethod
    def _smooth_mean(
        frame: pd.DataFrame,
        settings: ProcessingSettings,
    ) -> pd.DataFrame:
        """Post-aggregation smoothing on the mean frame."""
        if frame.empty:
            return frame

        result = frame

        # Temperature smoothing
        if settings.sg_mode:
            result = smooth_temperature_savitzky_golay(
                result, settings.sg_window, settings.sg_polyorder,
            )
        else:
            result = smooth_temperature(result, settings.temp_smoothing)

        # Derivative smoothing
        if settings.sg_mode:
            result = smooth_derivative_savitzky_golay(
                result, settings.sg_window, settings.sg_polyorder,
            )
        else:
            result = smooth_derivative(result, settings.span, settings.smooth_dmdt)

        return result

    @staticmethod
    def _round_frame(frame: pd.DataFrame) -> pd.DataFrame:
        """Round output frame for parity with legacy pipeline."""
        rounded = frame.copy()
        for column in ("temp", "time", "deltatemp"):
            if column in rounded.columns:
                rounded[column] = rounded[column].round(2)
        if "mass" in rounded.columns:
            rounded["mass"] = rounded["mass"].round(3)
        if "dmdt" in rounded.columns:
            rounded["dmdt"] = rounded["dmdt"].round(6)
        return rounded

    @staticmethod
    def _empty_result(file_names: list[str]) -> ProcessingResult:
        """Return an empty/placeholder result."""
        return ProcessingResult(
            combined=", ".join(file_names) if file_names else "",
            mass_smoothed=pd.DataFrame(),
            temp_smoothed=pd.DataFrame(),
            derivatives=pd.DataFrame(),
            peaks=[],
            summary=SummaryResult(
                lines=["Нет валидных термограмм для обработки"],
                metrics={"thermogram_count": 0, "processed_rows": 0, "peak_count": 0},
            ),
            heat_speed_text="Скорость нагрева: недоступна",
            metadata={"status": "no-valid-thermograms"},
        )