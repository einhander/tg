"""Ports for kinetics infrastructure."""

from __future__ import annotations

from abc import Protocol, abstractmethod
from pathlib import Path
from typing import Any, Mapping

from tgapp.domain.kinetics.models import (
    KineticRun,
    KineticStudy,
    KineticAnalysisResult,
)


class KineticRunRepository(Protocol):
    """Port for kinetic run persistence."""

    @abstractmethod
    def save_run(self, run: KineticRun) -> None: ...

    @abstractmethod
    def load_run(self, run_id: str) -> KineticRun: ...


class KineticStudyRepository(Protocol):
    """Port for kinetic study persistence."""

    @abstractmethod
    def save_study(self, study: KineticStudy) -> None: ...

    @abstractmethod
    def load_study(self, study_id: str) -> tuple[KineticStudy, dict[str, Any]]: ...

    @abstractmethod
    def save_analysis(self, result: KineticAnalysisResult) -> Path: ...

    @abstractmethod
    def load_analysis(self, study_id: str, analysis_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def list_analyses(self, study_id: str) -> list[str]: ...