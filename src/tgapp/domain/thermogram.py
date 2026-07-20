from __future__ import annotations

import numpy as np
import pandas as pd

from tgapp.domain.models import CorrectionFile, ThermogramFile


NORMALIZED_COLUMNS = ["temp", "deltatemp", "time", "mass"]


def normalize_thermogram_frame(frame: pd.DataFrame) -> pd.DataFrame:
    working = frame.copy()
    working.columns = [str(column).strip().lower() for column in working.columns]
    for column in NORMALIZED_COLUMNS:
        if column not in working.columns:
            working[column] = pd.Series(dtype="float64")
    ordered = working.loc[:, NORMALIZED_COLUMNS].copy()
    for column in NORMALIZED_COLUMNS:
        ordered[column] = pd.to_numeric(ordered[column], errors="coerce")
    ordered = ordered.dropna(how="all")
    return ordered.reset_index(drop=True)


def combine_thermograms(files: list[ThermogramFile]) -> pd.DataFrame:
    if not files:
        return pd.DataFrame(columns=[*NORMALIZED_COLUMNS, "series"])

    frames: list[pd.DataFrame] = []
    for item in files:
        normalized = normalize_thermogram_frame(item.frame)
        if normalized.empty:
            continue
        annotated = normalized.copy()
        annotated["series"] = item.name
        frames.append(annotated)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=[*NORMALIZED_COLUMNS, "series"])


def resample_thermogram(frame: pd.DataFrame, bins: int) -> pd.DataFrame:
    normalized = normalize_thermogram_frame(frame)
    if normalized.empty:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)

    target_bins = max(int(bins), 2)
    source_length = len(normalized.index)
    if source_length == target_bins:
        return normalized.reset_index(drop=True)
    if len(normalized.index) == 1:
        return pd.concat([normalized] * target_bins, ignore_index=True).iloc[:target_bins].reset_index(drop=True)

    if source_length > target_bins:
        return _bin_mean_resample(normalized, target_bins)

    return _interpolate_resample(normalized, target_bins)


def _interpolate_resample(frame: pd.DataFrame, target_bins: int) -> pd.DataFrame:
    base_index = np.linspace(0.0, 1.0, num=len(frame.index))
    target_index = np.linspace(0.0, 1.0, num=target_bins)
    resampled = pd.DataFrame(index=range(target_bins))
    for column in NORMALIZED_COLUMNS:
        source = frame[column].astype(float).to_numpy()
        resampled[column] = np.interp(target_index, base_index, source)
    return resampled

 
def _bin_mean_resample(frame: pd.DataFrame, target_bins: int) -> pd.DataFrame:
    edges = np.linspace(0, len(frame.index), num=target_bins + 1)
    resampled = pd.DataFrame(index=range(target_bins))
    for column in NORMALIZED_COLUMNS:
        source = frame[column].astype(float).to_numpy()
        values: list[float] = []
        for index in range(target_bins):
            start = int(round(edges[index]))
            stop = int(round(edges[index + 1]))
            if stop <= start:
                stop = min(start + 1, len(source))
            segment = source[start:stop]
            if len(segment) == 0:
                anchor = min(max(start, 0), len(source) - 1)
                values.append(float(source[anchor]))
            else:
                values.append(float(np.nanmean(segment)))
        resampled[column] = values
    return resampled


def compute_mean_traces(resampled_frames: list[pd.DataFrame]) -> pd.DataFrame:
    if not resampled_frames:
        return pd.DataFrame(columns=NORMALIZED_COLUMNS)

    stacked = np.stack([frame.loc[:, NORMALIZED_COLUMNS].to_numpy(dtype=float) for frame in resampled_frames], axis=0)
    means = stacked.mean(axis=0)
    return pd.DataFrame(means, columns=NORMALIZED_COLUMNS)


def compute_mean_correction(correction: CorrectionFile | None, bins: int) -> np.ndarray | None:
    if correction is None or correction.frame.empty:
        return None
    resampled = resample_thermogram(correction.frame, bins)
    if resampled.empty:
        return None
    return resampled["deltatemp"].round(5).to_numpy(dtype=float)
