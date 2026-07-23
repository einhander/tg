from __future__ import annotations

import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # pyright: ignore[reportMissingImports]

from tgapp.application.dto import PlotPayload
from tgapp.domain.models import ThermogramViewSettings
from tgapp.domain.peaks import detect_raw_plot_markers, detect_tg_inflection_markers
from tgapp.domain.processing_engine import compute_dmdt_per_run
from tgapp.domain.smoothing import smooth_series_savitzky_golay
from tgapp.infrastructure.serialization import _json_safe


DTG_PLOT_SCALE = 200.0
PLOT_TITLE = "Термограмма"
TG_TRACE_COLOR = "#009E73"
DTA_TRACE_COLOR = "#E69F00"
DTG_TRACE_COLOR = "#56B4E9"


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


def add_peak_markers(
    figure: go.Figure,
    peaks: list,
    settings: dict,
) -> None:
    """Add peak/valley markers to a figure. Shared between TGA1 and TGA2 plots."""
    for peak in peaks:
        peak_kind = str(peak.get("kind", "peak"))
        extremum = str(peak.get("extremum", "peak"))

        if peak_kind not in {"dta", "dtg"}:
            continue

        if peak_kind == "dta" and settings.get("hide_peaks_dta", False):
            continue
        if peak_kind == "dtg" and settings.get("hide_peaks_dmdt", False):
            continue

        peak_y = float(peak.get("y", 0.0))
        if peak_kind == "dtg":
            peak_y *= DTG_PLOT_SCALE
        color = DTA_TRACE_COLOR if peak_kind == "dta" else DTG_TRACE_COLOR
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


def _smooth_series_savgol(series: pd.Series, window: int, polyorder: int = 3) -> pd.Series:
    return smooth_series_savitzky_golay(series, window, polyorder)


def _add_tg_inflection_markers(figure: go.Figure, peaks: list[dict], hide_inflections_tg: bool, hide_tg: bool = False) -> None:
    if hide_inflections_tg or hide_tg:
        return

    for peak in peaks:
        if peak.get("kind") != "tg":
            continue

        peak_x = float(peak.get("x", 0.0))
        peak_y = float(peak.get("y", 0.0))
        figure.add_vline(x=peak_x, line_width=1, line_dash="dot", line_color=TG_TRACE_COLOR, opacity=0.3)
        figure.add_trace(
            go.Scatter(
                x=[peak_x],
                y=[peak_y],
                mode="markers+text",
                text=[peak.get("label", "inflection")],
                textposition="top center",
                name="ТГ перегиб",
                marker={"color": TG_TRACE_COLOR, "symbol": "diamond", "size": 9},
                showlegend=False,
                yaxis="y2",
            )
        )


def build_main_plot(payload: PlotPayload) -> go.Figure:
    figure = go.Figure()
    frame = pd.DataFrame(payload.frame_records)
    settings = payload.settings

    if not frame.empty:
        if not settings.get("hide_tg", False) and {"temp", "mass"}.issubset(frame.columns):
            figure.add_trace(
                go.Scatter(
                    x=frame["temp"],
                    y=frame["mass"],
                    mode="lines",
                    name="ТГ",
                    line={"color": TG_TRACE_COLOR},
                    yaxis="y2",
                    customdata=frame[["mass"]].to_numpy(),
                    hovertemplate="Температура=%{x}<br>Масса=%{customdata[0]}<extra></extra>",
                )
            )
        if not settings.get("hide_dta", False) and {"temp", "deltatemp"}.issubset(frame.columns):
            figure.add_trace(go.Scatter(x=frame["temp"], y=frame["deltatemp"], mode="lines", name="ДТА", line={"color": DTA_TRACE_COLOR}))
        if not settings.get("hide_dtg", False):
            dtg_col = "dmdt"
            if {"temp", dtg_col}.issubset(frame.columns):
                figure.add_trace(
                    go.Scatter(
                        x=frame["temp"],
                        y=frame[dtg_col] * DTG_PLOT_SCALE,
                        mode="lines",
                        name="ТГП",
                        line={"color": DTG_TRACE_COLOR},
                        customdata=frame[[dtg_col]].to_numpy(),
                        hovertemplate="Температура=%{x}<br>ТГП (масштаб)=%{y}<br>ТГП=%{customdata[0]}<extra></extra>",
                    )
                )

    main_markers = list(payload.peaks)
    main_markers.extend(asdict(marker) for marker in detect_tg_inflection_markers(frame, settings.get("peak_prominence_sigma", 5.0)))
    add_peak_markers(figure, main_markers, settings)
    _add_tg_inflection_markers(
        figure,
        main_markers,
        settings.get("hide_inflections_tg", False),
        settings.get("hide_tg", False),
    )

    # Compute mass range for yaxis2
    mass_range = None
    if not frame.empty and "mass" in frame.columns:
        mass_min = float(frame["mass"].min())
        mass_max = float(frame["mass"].max())
        mass_pad = (mass_max - mass_min) * 0.1 or 0.001
        mass_range = [mass_min - mass_pad, mass_max + mass_pad]

    # If TG is hidden, add an invisible anchor trace on y2 so the axis still renders
    if settings.get("hide_tg", False) and mass_range is not None:
        figure.add_trace(
            go.Scatter(
                x=[frame["temp"].iloc[0], frame["temp"].iloc[-1]],
                y=[mass_range[0], mass_range[0]],
                mode="lines",
                line={"color": "rgba(0,0,0,0)"},
                showlegend=False,
                yaxis="y2",
            )
        )

    figure.add_hline(y=0.0, line_color="#dc2626", line_width=1, opacity=0.5)
    yaxis2_cfg = {
        "title": "Масса, г",
        "overlaying": "y",
        "side": "right",
        "showgrid": False,
        "tickmode": "auto",
    }
    if mass_range is not None:
        yaxis2_cfg["range"] = mass_range

    figure.update_layout(
        title=payload.title or PLOT_TITLE,
        template="plotly_white",
        font={"family": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", "size": 13},
        title_font={"size": 16, "weight": 600},
        xaxis_title="Температура, °C",
        yaxis_title="Разница температур, °C",
        xaxis={"gridcolor": "#e5e7eb", "zerolinecolor": "#d1d5db"},
        yaxis={"gridcolor": "#e5e7eb", "zerolinecolor": "#d1d5db"},
        yaxis2=yaxis2_cfg,
        legend={"x": 0.02, "y": 0.1, "xanchor": "left", "yanchor": "bottom", "bgcolor": "rgba(255,255,255,0.8)", "bordercolor": "#e5e7eb", "borderwidth": 1},
        plot_bgcolor="white",
        paper_bgcolor="white",
    )

    return figure


def build_raw_plot(frame: pd.DataFrame, settings: ThermogramViewSettings | None = None) -> go.Figure:
    figure = go.Figure()
    plot_settings = settings or ThermogramViewSettings()
    plot_frame = frame.copy()

    # Apply separate SG smoothing to mass and deltatemp
    if plot_settings.sg_mode and not plot_frame.empty:
        if "mass" in plot_frame.columns:
            plot_frame["mass"] = _smooth_series_savgol(plot_frame["mass"], plot_settings.sg_mass_window)
        if "deltatemp" in plot_frame.columns:
            plot_frame["deltatemp"] = _smooth_series_savgol(plot_frame["deltatemp"], plot_settings.sg_temp_window)

    if not plot_settings.hide_tg and not plot_frame.empty and {"temp", "mass"}.issubset(plot_frame.columns):
        figure.add_trace(
            go.Scatter(
                x=plot_frame["temp"],
                y=plot_frame["mass"],
                mode="lines",
                name="ТГ",
                line={"color": TG_TRACE_COLOR},
                yaxis="y2",
                customdata=plot_frame[["mass"]].to_numpy(),
                hovertemplate="Температура=%{x}<br>Масса=%{customdata[0]}<extra></extra>",
            )
        )
    if not plot_settings.hide_dta and not plot_frame.empty and {"temp", "deltatemp"}.issubset(plot_frame.columns):
        figure.add_trace(go.Scatter(x=plot_frame["temp"], y=plot_frame["deltatemp"], mode="lines", name="ДТА", line={"color": DTA_TRACE_COLOR}))

    # Compute and add DTG trace from mass/time derivative
    if not plot_settings.hide_dtg and not plot_frame.empty and {"temp", "mass", "time"}.issubset(plot_frame.columns):
        dmdt = compute_dmdt_per_run(plot_frame)
        if dmdt.dropna().empty:
            dmdt = None
        if dmdt is not None and len(dmdt) == len(plot_frame):
            # Apply SG smoothing to DTG to reduce noise from finite-difference derivative
            if plot_settings.sg_mode:
                dmdt = _smooth_series_savgol(dmdt, plot_settings.sg_dtg_window)
            dmdt_arr = dmdt.to_numpy(dtype=np.float64)
            plot_frame["dmdt"] = dmdt_arr
            figure.add_trace(
                go.Scatter(
                    x=plot_frame["temp"],
                    y=dmdt_arr * DTG_PLOT_SCALE,
                    mode="lines",
                    name="ТГП",
                    line={"color": DTG_TRACE_COLOR},
                    customdata=dmdt_arr.reshape(-1, 1),
                    hovertemplate="Температура=%{x}<br>ТГП (масштаб)=%{y}<br>ТГП=%{customdata[0]}<extra></extra>",
                )
            )

    raw_markers = [asdict(marker) for marker in detect_raw_plot_markers(plot_frame, plot_settings)]
    add_peak_markers(figure, raw_markers, asdict(plot_settings))
    _add_tg_inflection_markers(figure, raw_markers, plot_settings.hide_inflections_tg, plot_settings.hide_tg)

    # Update axis title when DTG is visible
    yaxis_title = "ДТА / ТГП (масштаб), °C" if not plot_settings.hide_dtg else "Разница температур, °C"

    # Compute mass range for yaxis2
    mass_range = None
    if not plot_frame.empty and "mass" in plot_frame.columns:
        mass_min = float(plot_frame["mass"].min())
        mass_max = float(plot_frame["mass"].max())
        mass_pad = (mass_max - mass_min) * 0.1 or 0.001
        mass_range = [mass_min - mass_pad, mass_max + mass_pad]

    # If TG is hidden, add an invisible anchor trace on y2 so the axis still renders
    if plot_settings.hide_tg and mass_range is not None:
        figure.add_trace(
            go.Scatter(
                x=[plot_frame["temp"].iloc[0], plot_frame["temp"].iloc[-1]],
                y=[mass_range[0], mass_range[0]],
                mode="lines",
                line={"color": "rgba(0,0,0,0)"},
                showlegend=False,
                yaxis="y2",
            )
        )

    yaxis2_cfg = {
        "title": "Масса, г",
        "overlaying": "y",
        "side": "right",
        "showgrid": False,
        "tickmode": "auto",
    }
    if mass_range is not None:
        yaxis2_cfg["range"] = mass_range

    figure.update_layout(
        title=PLOT_TITLE,
        template="plotly_white",
        font={"family": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", "size": 13},
        title_font={"size": 16, "weight": 600},
        xaxis_title="Температура, °C",
        yaxis_title=yaxis_title,
        xaxis={"gridcolor": "#e5e7eb", "zerolinecolor": "#d1d5db"},
        yaxis={"gridcolor": "#e5e7eb", "zerolinecolor": "#d1d5db"},
        yaxis2=yaxis2_cfg,
        legend={"x": 0.02, "y": 0.98, "xanchor": "left", "yanchor": "top", "bgcolor": "rgba(255,255,255,0.8)", "bordercolor": "#e5e7eb", "borderwidth": 1},
        plot_bgcolor="white",
        paper_bgcolor="white",
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
        if hasattr(trace, "yaxis"):
            yaxis_val = trace.yaxis
            if yaxis_val and yaxis_val != "y1":
                trace_dict["yaxis"] = yaxis_val
        if hasattr(trace, "customdata") and trace.customdata is not None:
            trace_dict["customdata"] = trace.customdata.tolist() if isinstance(trace.customdata, np.ndarray) else list(trace.customdata)
        if hasattr(trace, "hovertemplate") and trace.hovertemplate:
            trace_dict["hovertemplate"] = trace.hovertemplate
        if hasattr(trace, "line") and trace.line:
            trace_dict["line"] = _convert(trace.line.to_plotly_json())
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
    figure.update_layout(
        title="Mixchar (deferred)",
        template="plotly_white",
        font={"family": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", "size": 13},
        plot_bgcolor="#f9fafb",
        paper_bgcolor="white",
    )
    figure.add_annotation(text="Mixchar migration placeholder", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return figure


def build_deconv_placeholder() -> go.Figure:
    figure = go.Figure()
    figure.update_layout(
        title="Deconvolution (deferred)",
        template="plotly_white",
        font={"family": "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif", "size": 13},
        plot_bgcolor="#f9fafb",
        paper_bgcolor="white",
    )
    figure.add_annotation(text="Deconvolution migration placeholder", x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    return figure
