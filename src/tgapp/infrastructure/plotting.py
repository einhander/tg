from __future__ import annotations

import json

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # pyright: ignore[reportMissingImports]

from tgapp.application.dto import PlotPayload
from tgapp.domain.models import Tga2PlotSettings
from tgapp.domain.smoothing import smooth_mass_savitzky_golay
from tgapp.infrastructure.serialization import _json_safe


DTG_PLOT_SCALE = 200.0
PLOT_TITLE = "Термограмма"


def _finite_range(series: pd.Series) -> float:
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return 0.0
    return float(numeric.max() - numeric.min())


def _mass_scale(frame: pd.DataFrame) -> float:
    if not {"mass", "deltatemp"}.issubset(frame.columns):
        return 1.0
    deltatemp_scale = _finite_range(frame["deltatemp"])
    mass_scale = _finite_range(frame["mass"])
    if deltatemp_scale == 0.0 or mass_scale == 0.0:
        return 1.0
    return deltatemp_scale / mass_scale


def build_main_plot(payload: PlotPayload) -> go.Figure:
    figure = go.Figure()
    frame = pd.DataFrame(payload.frame_records)
    settings = payload.settings
    mass_scale = _mass_scale(frame)

    if not frame.empty:
        if not settings.get("hide_tg", False) and {"temp", "mass"}.issubset(frame.columns):
            figure.add_trace(
                go.Scatter(
                    x=frame["temp"],
                    y=frame["mass"] * mass_scale,
                    mode="lines",
                    name="ТГ",
                    customdata=frame[["mass"]].to_numpy(),
                    hovertemplate="Температура=%{x}<br>ТГ (масштаб)=%{y}<br>Масса=%{customdata[0]}<extra></extra>",
                )
            )
        if not settings.get("hide_dta", False) and {"temp", "deltatemp"}.issubset(frame.columns):
            figure.add_trace(go.Scatter(x=frame["temp"], y=frame["deltatemp"], mode="lines", name="ДТА"))
        if not settings.get("hide_dtg", False):
            dtg_col = "dmdt"
            if {"temp", dtg_col}.issubset(frame.columns):
                figure.add_trace(
                    go.Scatter(
                        x=frame["temp"],
                        y=frame[dtg_col] * DTG_PLOT_SCALE,
                        mode="lines",
                        name="ТГП",
                        customdata=frame[[dtg_col]].to_numpy(),
                        hovertemplate="Температура=%{x}<br>ТГП (масштаб)=%{y}<br>ТГП=%{customdata[0]}<extra></extra>",
                    )
                )

    for peak in payload.peaks:
        peak_kind = str(peak.get("kind", "peak"))
        extremum = str(peak.get("extremum", "peak"))
        if peak_kind == "dta" and settings.get("hide_peaks_dta", False):
            continue
        if peak_kind == "dtg" and settings.get("hide_peaks_dmdt", False):
            continue

        peak_y = float(peak.get("y", 0.0))
        if peak_kind == "dtg":
            peak_y *= DTG_PLOT_SCALE
        color = "#E69F00" if peak_kind == "dta" else "#56B4E9"
        symbol = "triangle-up" if extremum == "peak" else "triangle-down"
        text_position = "top center" if extremum == "peak" else "bottom center"

        figure.add_vline(x=float(peak.get("x", 0.0)), line_width=1, line_dash="dot", line_color=color, opacity=0.35)
        figure.add_trace(
            go.Scatter(
                x=[peak.get("x", 0.0)],
                y=[peak_y],
                mode="markers+text",
                text=[peak.get("label", "peak")],
                textposition=text_position,
                name=f"{'ДТА' if peak_kind == 'dta' else 'ТГП'} {'пик' if extremum == 'peak' else 'впадина'}",
                marker={"color": color, "symbol": symbol, "size": 9},
                showlegend=False,
            )
        )

    figure.add_hline(y=0.0, line_color="coral", line_width=1, opacity=0.5)
    figure.update_layout(
        title=payload.title or PLOT_TITLE,
        template="plotly_white",
        xaxis_title="Температура, °C",
        yaxis_title="Разница температур, °C",
        yaxis2={
            "title": "Масса, г",
            "overlaying": "y",
            "side": "right",
            "showgrid": False,
            "tickmode": "auto",
        },
        legend={"x": 0.02, "y": 0.02, "xanchor": "left", "yanchor": "bottom"},
    )

    if not frame.empty and mass_scale not in (0.0, 1.0) and {"mass", "deltatemp"}.issubset(frame.columns):
        primary_ticks = figure.layout.yaxis.tickvals
        if primary_ticks:
            figure.update_layout(yaxis2={**figure.layout.yaxis2.to_plotly_json(), "tickvals": primary_ticks, "ticktext": [f"{tick / mass_scale:.3f}" for tick in primary_ticks]})

    return figure


def _smooth_series_savgol(series: pd.Series, window: int, polyorder: int = 3) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    values = numeric.to_numpy(dtype=float)
    valid = np.isfinite(values)
    if valid.sum() < 3:
        return numeric

    smoothed = numeric.copy()
    filtered = smooth_mass_savitzky_golay(pd.DataFrame({"mass": values[valid]}), window, polyorder)["mass"].to_numpy(dtype=float)
    smoothed.loc[valid] = filtered
    return smoothed


def build_raw_plot(frame: pd.DataFrame, settings: Tga2PlotSettings | None = None) -> go.Figure:
    figure = go.Figure()
    plot_settings = settings or Tga2PlotSettings()
    plot_frame = frame.copy()

    if plot_settings.sg_mode and not plot_frame.empty:
        if "mass" in plot_frame.columns:
            plot_frame["mass"] = _smooth_series_savgol(plot_frame["mass"], plot_settings.sg_window)
        if "deltatemp" in plot_frame.columns:
            plot_frame["deltatemp"] = _smooth_series_savgol(plot_frame["deltatemp"], plot_settings.sg_window)

    if not plot_settings.hide_tg and not plot_frame.empty and {"temp", "mass"}.issubset(plot_frame.columns):
        figure.add_trace(go.Scatter(x=plot_frame["temp"], y=plot_frame["mass"], mode="lines", name="ТГ"))
    if not plot_settings.hide_dta and not plot_frame.empty and {"temp", "deltatemp"}.issubset(plot_frame.columns):
        figure.add_trace(go.Scatter(x=plot_frame["temp"], y=plot_frame["deltatemp"], mode="lines", name="ДТА"))

    figure.update_layout(
        title=PLOT_TITLE,
        template="plotly_white",
        xaxis_title="Температура, °C",
        yaxis_title="Значение",
        legend={"x": 0.02, "y": 0.98, "xanchor": "left", "yanchor": "top"},
    )
    return figure


def figure_to_json(figure: go.Figure) -> str:
    """Convert Plotly figure to JSON string with actual arrays for frontend."""

    def _convert(obj):
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.generic):
            return obj.item()
        if isinstance(obj, dict):
            return {key: _convert(value) for key, value in obj.items()}
        if isinstance(obj, list):
            return [_convert(item) for item in obj]
        if hasattr(obj, "to_plotly_json"):
            return _convert(obj.to_plotly_json())
        return obj

    data = []
    for trace in figure.data:
        trace_dict = {
            "type": trace.type,
            "mode": trace.mode,
            "name": trace.name,
            "x": trace.x.tolist() if isinstance(trace.x, np.ndarray) else list(trace.x),
            "y": trace.y.tolist() if isinstance(trace.y, np.ndarray) else list(trace.y),
        }
        if hasattr(trace, "customdata") and trace.customdata is not None:
            trace_dict["customdata"] = trace.customdata.tolist() if isinstance(trace.customdata, np.ndarray) else list(trace.customdata)
        if hasattr(trace, "hovertemplate") and trace.hovertemplate:
            trace_dict["hovertemplate"] = trace.hovertemplate
        if hasattr(trace, "marker") and trace.marker:
            trace_dict["marker"] = _convert(trace.marker.to_plotly_json())
        if hasattr(trace, "text") and trace.text:
            trace_dict["text"] = list(trace.text)
        if hasattr(trace, "textposition") and trace.textposition:
            trace_dict["textposition"] = trace.textposition
        if hasattr(trace, "showlegend") and trace.showlegend is not None:
            trace_dict["showlegend"] = trace.showlegend
        data.append(trace_dict)

    layout = _convert(figure.layout.to_plotly_json())
    result = _json_safe({"data": data, "layout": layout})
    return json.dumps(result, default=str, allow_nan=False)


def build_mixchar_placeholder() -> go.Figure:
    figure = go.Figure()
    figure.update_layout(title="Mixchar (deferred)", template="plotly_white")
    figure.add_annotation(text="Mixchar migration placeholder", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return figure


def build_deconv_placeholder() -> go.Figure:
    figure = go.Figure()
    figure.update_layout(title="Deconvolution (deferred)", template="plotly_white")
    figure.add_annotation(text="Deconvolution migration placeholder", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return figure
