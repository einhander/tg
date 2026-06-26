from __future__ import annotations

import math

import pandas as pd

from tgapp.domain.models import PeakResult, ProcessingSettings


def _window_from_span(length: int, span: float) -> int:
    if length < 3:
        return 1
    raw_window = (2 * round((((100.0 - min(max(span, 1.0), 100.0)) * length) / 100.0) / 2.0)) - 1
    window = max(int(raw_window), 3)
    if window % 2 == 0:
        window -= 1
    return min(window, length if length % 2 == 1 else length - 1)


def _half_window(length: int, span: float) -> int:
    return max((_window_from_span(length, span) - 1) // 2, 1)


def _detect_trace_extrema(frame: pd.DataFrame, y_column: str, trace_kind: str, span: float) -> list[PeakResult]:
    if frame.empty or "temp" not in frame.columns or y_column not in frame.columns:
        return []

    valid = frame.loc[:, ["temp", y_column]].dropna().reset_index(drop=True)
    if len(valid.index) < 3:
        return []

    window = _half_window(len(valid.index), span)
    results: list[PeakResult] = []
    for index in range(window, len(valid.index) - window):
        segment = valid.iloc[index - window : index + window + 1]
        center_y = float(valid.iloc[index][y_column])
        center_x = float(valid.iloc[index]["temp"])
        segment_max = float(segment[y_column].max())
        segment_min = float(segment[y_column].min())

        left_y = float(valid.iloc[index - 1][y_column])
        right_y = float(valid.iloc[index + 1][y_column])
        prominence = segment_max - segment_min

        if center_y == segment_max and center_y >= left_y and center_y > right_y and prominence > 0:
            results.append(PeakResult(x=center_x, y=center_y, label=f"{center_x:.1f}", kind=trace_kind, extremum="peak"))
        elif center_y == segment_min and center_y <= left_y and center_y < right_y and prominence > 0:
            results.append(PeakResult(x=center_x, y=center_y, label=f"{center_x:.1f}", kind=trace_kind, extremum="valley"))

    return _dedupe_extrema(results, window)


def _dedupe_extrema(results: list[PeakResult], window: int) -> list[PeakResult]:
    if not results:
        return []
    deduped: list[PeakResult] = []
    min_distance = max(window, 1)
    for peak in sorted(results, key=lambda item: (item.kind, item.extremum, item.x)):
        if not deduped:
            deduped.append(peak)
            continue
        previous = deduped[-1]
        same_group = previous.kind == peak.kind and previous.extremum == peak.extremum and abs(previous.x - peak.x) <= min_distance
        if same_group:
            if abs(peak.y) >= abs(previous.y):
                deduped[-1] = peak
        else:
            deduped.append(peak)
    return deduped


def detect_peaks(frame: pd.DataFrame, settings: ProcessingSettings) -> list[PeakResult]:
    peaks: list[PeakResult] = []
    peaks.extend(_detect_trace_extrema(frame, "deltatemp", "dta", settings.span))
    peaks.extend(_detect_trace_extrema(frame, "dmdt", "dtg", settings.span))
    return peaks
