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
    CorrectionRangeError,
    DerivativeCalculationError,
    PeakResult,
    ProcessingSettings,
    SummaryResult,
    ThermogramFile,
    ValidatedThermogram,
)
from tgapp.domain.peaks import detect_peaks
from tgapp.domain.smoothing import (
    smooth_column_savitzky_golay,
    smooth_derivative,
    smooth_derivative_savitzky_golay,
    smooth_mass,
)
from tgapp.domain.summary import build_heat_speed_text, build_summary


logger = logging.getLogger(__name__)

TIME_EPSILON = 1e-9


def compute_dmdt_per_run(frame: pd.DataFrame) -> pd.Series:
    """Calculate dm/dt for one experiment via np.gradient.

    Uses central differences (np.gradient), which give
    second-order accurate derivative.

    Args:
        frame: DataFrame with 'mass' and 'time' columns

    Returns:
        Series with dm/dt in mass/time units
    """
    if frame.empty or "mass" not in frame.columns or "time" not in frame.columns:
        return pd.Series([np.nan] * len(frame), name="dmdt", dtype="float64", index=frame.index)

    mass = frame["mass"].to_numpy(dtype=float)
    time = frame["time"].to_numpy(dtype=float)

    dmdt = np.gradient(mass, time)

    return pd.Series(dmdt, name="dmdt", dtype="float64", index=frame.index)


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
    peaks: tuple[PeakResult, ...]
    summary: SummaryResult
    heat_speed_text: str
    metadata: dict = field(default_factory=dict)
    per_run: tuple[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray | None, np.ndarray], ...] = field(default_factory=tuple)  # Per-experiment traces

    


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

        # 1. Determine common physical range & align
        aligned = self._align(validated, effective_settings.bins)

        # 3. Apply temperature correction (if enabled)
        corrected = self._apply_correction(aligned, correction, effective_settings.use_correction)

        # 4. Smooth each experiment individually
        smoothed = self._smooth_each(corrected, effective_settings)

        # 5. Calculate dm/dt for each experiment
        dmdt_traces = [self._compute_dmdt(frame) for frame in smoothed]

        # 5b. Collect per-run data
        per_run_data = []
        for i, frame in enumerate(smoothed):
            run_data = (
                smoothed[i]["mass"].to_numpy(dtype=float),
                smoothed[i]["time"].to_numpy(dtype=float),
                smoothed[i]["temp"].to_numpy(dtype=float),
                smoothed[i].get("deltatemp", pd.Series(dtype=float)).to_numpy(dtype=float) if "deltatemp" in smoothed[i].columns else None,
                dmdt_traces[i].to_numpy(dtype=float),
            )
            per_run_data.append(run_data)

        per_run = tuple(per_run_data)

        # 6. Aggregate traces (mean)
        mean_frame = self._aggregate_traces(smoothed, dmdt_traces, effective_settings)

        # 7. Post-aggregation smoothing
        mean_frame = self._smooth_mean(mean_frame, effective_settings)

        # 8. Detect peaks on unrounded data
        peaks = detect_peaks(mean_frame, effective_settings)

        # 9. Round for output
        mean_frame = self._round_frame(mean_frame)

        # 10. Build summary & heat speed
        file_names = [v.name for v in validated]
        summary = build_summary(
            [ThermogramFile(name=n) for n in file_names],
            mean_frame,
            peaks,
        )
        heat_speed = build_heat_speed_text(mean_frame)

        # 10. Assemble immutable result
        return ProcessingResult(
            combined=", ".join(file_names),
            mass_smoothed=mean_frame.loc[
                :, [c for c in ("temp", "mass") if c in mean_frame.columns]
            ].copy(),
            temp_smoothed=mean_frame.loc[
                :, [c for c in ("time", "temp", "deltatemp") if c in mean_frame.columns]
            ].copy(),
            derivatives=mean_frame.copy(),
            peaks=tuple(peaks),
            summary=summary,
            heat_speed_text=heat_speed,
            metadata={
                "correction_applied": effective_settings.use_correction and correction is not None,
                "settings": asdict(effective_settings),
                "thermogram_count": len(validated),
                "derivative_definition": "dm/dt",
                "derivative_units": "масса/время",
                "gradient_method": "numpy.gradient",
                "gradient_edge_order": 2,
                "per_run_derivative": True,
                "processing_version": "2.0",
            },
            per_run=per_run,
        )

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

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
        """Apply temperature correction to aligned thermograms.

        If use_correction is True and correction is None → raise CorrectionRangeError.
        If correction fails → re-raise the exception (no silent skip).
        """
        if not use_correction or correction is None:
            return aligned

        # If correction is requested but missing, raise
        if correction is None:
            raise CorrectionRangeError(
                "Температурная коррекция запрошена, но correction-файл не загружен."
            )

        # Apply correction — let exceptions propagate
        return apply_correction_to_aligned(aligned, correction)

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
        """Calculate dm/dt for one experiment via np.gradient.

        Pre-conditions (caller must ensure):
        - frame not empty
        - 'mass' and 'time' columns present
        - time strictly increasing
        - all values finite
        """
        if frame.empty or "mass" not in frame.columns or "time" not in frame.columns:
            raise DerivativeCalculationError("Недостаточно данных для расчёта производной: отсутствуют колонки mass или time")

        if len(frame) < 3:
            raise DerivativeCalculationError(f"Недостаточно точек для производной: {len(frame)} < 3")

        mass = frame["mass"].to_numpy(dtype=float)
        time = frame["time"].to_numpy(dtype=float)

        if not np.all(np.isfinite(mass)):
            raise DerivativeCalculationError("Масса содержит NaN/inf")
        if not np.all(np.isfinite(time)):
            raise DerivativeCalculationError("Время содержит NaN/inf")

        time_diffs = np.diff(time)
        if np.any(time_diffs <= 1e-9):
            raise DerivativeCalculationError("Время не строго возрастает")

        dmdt = np.gradient(mass, time, edge_order=2)
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
            raise DerivativeCalculationError("Нет данных для усреднения производной")

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
    def _smooth_mean(
        frame: pd.DataFrame,
        settings: ProcessingSettings,
    ) -> pd.DataFrame:
        """Post-aggregation smoothing on the mean frame.

        IMPORTANT: Only signal columns are smoothed (mass, deltatemp, dmdt).
        Physical axes (temp, time) are NEVER smoothed.
        """
        if frame.empty:
            return frame

        result = frame

        # NO temperature smoothing — temp is a physical axis
        # Only smooth signals: deltatemp, dmdt

        # Derivative smoothing (DTG)
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
            peaks=(),
            summary=SummaryResult(
                lines=["Нет валидных термограмм для обработки"],
                metrics={"thermogram_count": 0, "processed_rows": 0, "peak_count": 0},
            ),
            heat_speed_text="Скорость нагрева: недоступна",
            metadata={"status": "no-valid-thermograms"},
        )