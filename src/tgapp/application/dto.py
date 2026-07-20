from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class UploadPayload:
    filename: str | None = None
    content_type: str | None = None
    content: str | None = None


@dataclass(slots=True)
class UiMessage:
    level: str = "info"
    text: str = ""


@dataclass(slots=True)
class PlotPayload:
    frame_records: list[dict[str, Any]] = field(default_factory=list)
    peaks: list[dict[str, Any]] = field(default_factory=list)
    settings: dict[str, Any] = field(default_factory=dict)
    title: str = "Thermogram"


@dataclass(slots=True)
class SessionStateDto:
    session_id: str | None = None
    session_dir: str | None = None
    thermogram_files: list[str] = field(default_factory=list)
    validated_thermograms: list[str] = field(default_factory=list)
    correction_file: str | None = None
    imported_archive: str | None = None
    status: str = "empty"
    messages: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class ProcessingStateDto:
    settings: dict[str, Any] = field(default_factory=dict)
    processed_ready: bool = False
    summary: dict[str, Any] = field(default_factory=dict)
    heat_speed_text: str = "Heat speed: unavailable"
    effect_text: str = "Effect model deferred"
