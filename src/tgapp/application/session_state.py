from __future__ import annotations

from dataclasses import asdict

from tgapp.application.dto import ProcessingStateDto, SessionStateDto
from tgapp.domain.models import ProcessingSettings


def create_default_session_state() -> dict[str, object]:
    return asdict(SessionStateDto())


def create_default_processing_state() -> dict[str, object]:
    return asdict(
        ProcessingStateDto(
            settings=asdict(ProcessingSettings()),
            processed_ready=False,
        )
    )
