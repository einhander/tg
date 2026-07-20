from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Any, cast

from tgapp.domain.models import PeakResult, SummaryResult, ThermogramFile


EFFECT_SCALE_K = 0.4458333


def build_summary(files: list[ThermogramFile], frame: pd.DataFrame, peaks: list[PeakResult]) -> SummaryResult:
    preview_rows = _summary_preview_rows(frame)
    metrics = {
        "thermogram_count": len(files),
        "processed_rows": len(frame.index),
        "peak_count": len(peaks),
        "columns": list(frame.columns),
    }
    lines = [
        f"Термограмм загружено: {metrics['thermogram_count']}",
        f"Строк обработанных данных: {metrics['processed_rows']}",
        f"Найдено пиков: {metrics['peak_count']}",
    ]
    if files:
        lines.append("Файлы: " + ", ".join(item.name for item in files))
    if preview_rows:
        lines.append("")
        lines.append("Первые строки обработанных данных:")
        lines.extend(preview_rows)
    return SummaryResult(lines=lines, metrics=metrics)


def _summary_preview_rows(frame: pd.DataFrame, limit: int = 8) -> list[str]:
    if frame.empty:
        return []
    columns = [column for column in ("temp", "mass", "time", "deltatemp", "dmdt") if column in frame.columns]
    if not columns:
        return []
    preview = frame.loc[:, columns].head(limit).copy()
    for column in columns:
        numeric_values = cast(Any, pd.to_numeric(preview[column], errors="coerce"))
        preview[column] = [
            "NA" if pd.isna(value) else f"{float(value):.5g}"
            for value in numeric_values
        ]
    rows = ["\t".join(columns)]
    rows.extend("\t".join(str(row[column]) for column in columns) for _, row in preview.iterrows())
    return rows


def build_heat_speed_text(frame: pd.DataFrame) -> str:
    if frame.empty or "temp" not in frame.columns or "time" not in frame.columns:
        return "Скорость нагрева: недоступна"

    data = frame.loc[:, ["temp", "time"]].dropna()
    if len(data) < 2:
        return "Скорость нагрева: недоступна"

    temp = data["temp"].to_numpy(dtype=float)
    time = data["time"].to_numpy(dtype=float)

    # Проверить что время строго возрастает
    if np.any(time[1:] <= time[:-1]):
        return "Скорость нагрева: недоступна (немонотонное время)"

    # Линейная регрессия T(t) = T0 + βt
    # β = cov(T, t) / var(t)
    t_mean = np.mean(time)
    T_mean = np.mean(temp)

    numerator = np.sum((time - t_mean) * (temp - T_mean))
    denominator = np.sum((time - t_mean) ** 2)

    if denominator == 0:
        return "Скорость нагрева: недоступна"

    beta = numerator / denominator

    # Проверить качество линейного приближения (R²)
    T_predicted = T_mean + beta * (time - t_mean)
    T_residual = temp - T_predicted
    T_ss_res = np.sum(T_residual ** 2)
    T_ss_tot = np.sum((temp - T_mean) ** 2)

    r_squared = 1 - (T_ss_res / T_ss_tot) if T_ss_tot > 0 else 0

    # Если R² < 0.9, нагрев существенно нелинеен
    linearity_warning = ""
    if r_squared < 0.9:
        linearity_warning = " (средняя скорость, нагрев нелинеен)"

    return f"Скорость нагрева: {beta:.1f} K/мин{linearity_warning}"


def build_effect_text(frame: pd.DataFrame, xmin: float | None, xmax: float | None, init_mass: float) -> str:
    if frame.empty or not {"temp", "deltatemp"}.issubset(frame.columns):
        return "Тепловой эффект: выделите температурный интервал"
    if xmin is None or xmax is None:
        return "Тепловой эффект: выделите температурный интервал"
    left, right = sorted((round(float(xmin), 0), round(float(xmax), 0)))
    if left == right:
        return "Тепловой эффект: выделите температурный интервал"

    selection = frame.loc[:, ["temp", "deltatemp"]].dropna()
    selection = selection[(selection["temp"] > left) & (selection["temp"] < right)].sort_values("temp")
    if len(selection.index) < 2:
        return "Тепловой эффект: слишком мало точек"

    shifted = selection.copy()
    shifted["deltatemp"] = shifted["deltatemp"] - float(shifted.iloc[0]["deltatemp"])
    first = shifted.iloc[0]
    last = shifted.iloc[-1]
    triangle_area = 0.5 * (float(last["temp"]) - float(first["temp"])) * float(last["deltatemp"])
    trapz_area = float(np.trapezoid(shifted["deltatemp"].to_numpy(dtype=float), shifted["temp"].to_numpy(dtype=float)))
    effect = trapz_area - triangle_area
    mass = float(init_mass)
    if mass == 0:
        return "Тепловой эффект: начальная масса должна быть ненулевой"
    scaled_effect = EFFECT_SCALE_K * effect / mass
    return f"Тепловой эффект: {scaled_effect:.6g} Дж/г"
