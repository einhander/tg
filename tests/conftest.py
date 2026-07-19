from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from tgapp.domain.models import ProcessingSettings, ThermogramFile
from tgapp.infrastructure.file_parsers import _read_frame
from tgapp.web.app import create_app


# ---------------------------------------------------------------------------
# Paths to sample files (relative to repo root)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SAMPLE_SOSNA = _REPO_ROOT / "samples" / "Сосна" / "Сосна 600_10_250мг.dat"
_SAMPLE_BIRZA = _REPO_ROOT / "samples" / "Береза" / "Береза600_10_3140.dat"


@pytest.fixture
def sample_sosna_path() -> Path:
    """Path to the Сосна sample thermogram file."""
    assert _SAMPLE_SOSNA.exists(), f"Sample file missing: {_SAMPLE_SOSNA}"
    return _SAMPLE_SOSNA


@pytest.fixture
def sample_birza_path() -> Path:
    """Path to the Береза sample thermogram file."""
    assert _SAMPLE_BIRZA.exists(), f"Sample file missing: {_SAMPLE_BIRZA}"
    return _SAMPLE_BIRZA


@pytest.fixture
def sample_thermogram_frame(sample_sosna_path: Path) -> pd.DataFrame:
    """Parse the Сосна sample file into a DataFrame via _read_frame."""
    raw = sample_sosna_path.read_bytes()
    return _read_frame(raw)


@pytest.fixture
def processing_settings() -> ProcessingSettings:
    """ProcessingSettings with default parameters."""
    return ProcessingSettings()


@pytest.fixture
def client():
    """httpx.TestClient for the FastAPI app."""
    import httpx

    app = create_app()
    with httpx.TestClient(app) as test_client:
        yield test_client