from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pandas as pd


@dataclass(slots=True)
class ThermogramFile:
    name: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    source_kind: str = "upload"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CorrectionFile:
    name: str
    frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProcessingSettings:
    init_mass: float = 1.0
    bins: int = 1000
    mass_smoothing: int = 1
    temp_smoothing: int = 1
    difflag: int = 1
    use_correction: bool = False
    smooth_dmdt: bool = False
    span: float = 91
    sg_mode: bool = False
    sg_window: int = 11
    sg_polyorder: int = 3
    hide_tg: bool = False
    hide_dta: bool = False
    hide_dtg: bool = False
    hide_peaks_dta: bool = False
    hide_peaks_dmdt: bool = False


@dataclass(slots=True)
class Tga2PlotSettings:
    sg_mode: bool = False
    sg_window: int = 11
    hide_tg: bool = False
    hide_dta: bool = False


@dataclass(slots=True)
class PeakResult:
    x: float
    y: float
    label: str = "peak"
    kind: str = "dtg"
    extremum: str = "peak"


@dataclass(slots=True)
class SummaryResult:
    lines: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ThermogramProcessed:
    combined: pd.DataFrame = field(default_factory=pd.DataFrame)
    mass_smoothed: pd.DataFrame = field(default_factory=pd.DataFrame)
    temp_smoothed: pd.DataFrame = field(default_factory=pd.DataFrame)
    derivatives: pd.DataFrame = field(default_factory=pd.DataFrame)
    mean_frame: pd.DataFrame = field(default_factory=pd.DataFrame)
    peaks: list[PeakResult] = field(default_factory=list)
    summary: SummaryResult = field(default_factory=SummaryResult)
    heat_speed_text: str = "Heat speed unavailable"
    adjusted_difflag: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)
