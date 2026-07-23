from __future__ import annotations

from abc import ABC, abstractmethod

from tgapp.domain.kinetics.models import IsoconversionalDataset, KineticAnalysisResult


class BaseKineticMethod(ABC):
    """Базовый класс для изоконверсионных методов."""

    method_id: str = "base"
    display_name: str = "Base"
    method_version: str = "0.0"

    @abstractmethod
    def analyze(
        self,
        dataset: IsoconversionalDataset,
    ) -> KineticAnalysisResult:
        """Perform kinetic analysis on the isoconversional dataset."""
        ...