"""End-to-end integration tests per PLAN_AUDIT §19.2 (Этап 19.2).

Covers the full request/response pipeline:
  1. Session creation
  2. Single file upload
  3. Multiple file upload
  4. Correction file upload
  5. Processing
  6. Plot data retrieval
  7. Effect calculation
  8. Export and re-import
  9. Error handling for corrupted files
  10. APP_BASE_PATH=/tg
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tgapp.web.app import create_app
from tgapp.config import AppConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_dat_path() -> Path:
    """Path to the Береза sample thermogram file."""
    p = Path(__file__).resolve().parent.parent.parent / "samples" / "Береза" / "Береза600_10_3140.dat"
    assert p.exists(), f"Sample file missing: {p}"
    return p


# ---------------------------------------------------------------------------
# Test 1 — Session creation
# ---------------------------------------------------------------------------

class TestSessionCreation:
    """PLAN_AUDIT §19.2 п.1: создание сессии."""

    def test_create_session(self, client: TestClient):
        """GET / creates a session and sets tgapp_session_id cookie."""
        resp = client.get("/")
        assert resp.status_code == 200
        cookie = resp.cookies.get("tgapp_session_id")
        assert cookie is not None
        assert len(cookie) == 32  # UUID hex = 32 chars


# ---------------------------------------------------------------------------
# Test 2 — Single file upload
# ---------------------------------------------------------------------------

class TestSingleFileUpload:
    """PLAN_AUDIT §19.2 п.2: загрузка одного файла."""

    def test_upload_single_file(self, client: TestClient, sample_dat_path: Path, tmp_path: Path):
        """Upload one .dat file → response contains 'Loaded 1 thermogram'."""
        tmp_file = tmp_path / "test.dat"
        tmp_file.write_bytes(sample_dat_path.read_bytes())
        resp = client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", tmp_file.read_bytes(), "text/plain")},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Loaded 1 thermogram" in resp.text


# ---------------------------------------------------------------------------
# Test 3 — Multiple file upload
# ---------------------------------------------------------------------------

class TestMultipleFileUpload:
    """PLAN_AUDIT §19.2 п.3: загрузка нескольких файлов."""

    def test_upload_multiple_files(self, client: TestClient, sample_dat_path: Path, tmp_path: Path):
        """Upload two .dat files → response contains 'Loaded 2 thermogram'."""
        data = sample_dat_path.read_bytes()
        files = [
            ("thermograms", ("test1.dat", data, "text/plain")),
            ("thermograms", ("test2.dat", data, "text/plain")),
        ]
        resp = client.post(
            "/upload/thermograms",
            files=files,
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Loaded 2 thermogram" in resp.text


# ---------------------------------------------------------------------------
# Test 4 — Correction file upload
# ---------------------------------------------------------------------------

class TestCorrectionUpload:
    """PLAN_AUDIT §19.2 п.4: загрузка correction-файла."""

    def test_upload_correction(self, client: TestClient):
        """Upload a correction CSV → 200 with confirmation."""
        csv_content = b"temp,deltatemp\n100,0.5\n200,1.0\n300,0.5\n"
        resp = client.post(
            "/upload/correction",
            files={"correction": ("correction.csv", csv_content, "text/csv")},
            follow_redirects=False,
        )
        assert resp.status_code == 200
        assert "Loaded correction file" in resp.text


# ---------------------------------------------------------------------------
# Test 5 — Processing
# ---------------------------------------------------------------------------

class TestProcessing:
    """PLAN_AUDIT §19.2 п.5: обработка."""

    def test_process_thermograms(self, client: TestClient, sample_dat_path: Path, tmp_path: Path):
        """Upload + process → response contains heat speed text."""
        tmp_file = tmp_path / "test.dat"
        tmp_file.write_bytes(sample_dat_path.read_bytes())

        # Upload
        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", tmp_file.read_bytes(), "text/plain")},
            follow_redirects=False,
        )

        # Process
        resp = client.post("/process", follow_redirects=True)
        assert resp.status_code == 200
        assert "processed" in resp.text.lower() or "Скорость нагрева" in resp.text


# ---------------------------------------------------------------------------
# Test 6 — Plot data
# ---------------------------------------------------------------------------

class TestPlotData:
    """PLAN_AUDIT §19.2 п.6: получение графика."""

    def test_get_plot_data(self, client: TestClient, sample_dat_path: Path, tmp_path: Path):
        """Upload + process → response contains plot JSON data."""
        tmp_file = tmp_path / "test.dat"
        tmp_file.write_bytes(sample_dat_path.read_bytes())

        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", tmp_file.read_bytes(), "text/plain")},
            follow_redirects=False,
        )
        resp = client.post("/process", follow_redirects=True)
        assert resp.status_code == 200
        # Plotly figure serialized as JSON contains "data" / "traces" keys
        assert "data" in resp.text or "traces" in resp.text


# ---------------------------------------------------------------------------
# Test 7 — Effect calculation
# ---------------------------------------------------------------------------

class TestEffectCalculation:
    """PLAN_AUDIT §19.2 п.7: расчёт эффекта."""

    def test_calculate_effect(self, client: TestClient, sample_dat_path: Path, tmp_path: Path):
        """Upload + process + POST /effect → response contains 'Тепловой эффект'."""
        tmp_file = tmp_path / "test.dat"
        tmp_file.write_bytes(sample_dat_path.read_bytes())

        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", tmp_file.read_bytes(), "text/plain")},
            follow_redirects=False,
        )
        client.post("/process", follow_redirects=False)

        resp = client.post("/effect", data={"xmin": "100", "xmax": "500"})
        assert resp.status_code == 200
        assert "Тепловой эффект" in resp.text


# ---------------------------------------------------------------------------
# Test 8 — Export and re-import
# ---------------------------------------------------------------------------

class TestExportReimport:
    """PLAN_AUDIT §19.2 п.8: экспорт и повторный импорт сессии."""

    def test_export_and_reimport(self, client: TestClient, sample_dat_path: Path, tmp_path: Path):
        """Export session as ZIP → re-import → 200."""
        tmp_file = tmp_path / "test.dat"
        tmp_file.write_bytes(sample_dat_path.read_bytes())

        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", tmp_file.read_bytes(), "text/plain")},
            follow_redirects=False,
        )
        client.post("/process", follow_redirects=False)

        # Export
        resp = client.get("/export/session")
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/octet-stream"
        assert "content-disposition" in resp.headers

        # Re-import
        resp = client.post(
            "/upload/session",
            files={"session_file": ("session.tg", resp.content, "application/zip")},
            follow_redirects=True,
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Test 9 — Error handling for corrupted files
# ---------------------------------------------------------------------------

class TestCorruptedFileError:
    """PLAN_AUDIT §19.2 п.9: ошибки повреждённых файлов."""

    def test_corrupted_file_error(self, client: TestClient):
        """Upload non-CSV binary → 200/422, no traceback or internal paths."""
        corrupted = b"This is not a CSV file\x00\x01\x02"
        resp = client.post(
            "/upload/thermograms",
            files={"thermograms": ("corrupted.dat", corrupted, "text/plain")},
            follow_redirects=False,
        )
        assert resp.status_code in (200, 303, 307, 400, 422)
        # Should NOT contain traceback or internal paths
        assert "Traceback" not in resp.text
        assert 'File "' not in resp.text
        assert "/home/" not in resp.text


# ---------------------------------------------------------------------------
# Test 10 — APP_BASE_PATH=/tg
# ---------------------------------------------------------------------------

@pytest.fixture
def client_with_base_path(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient for an app mounted at /tg base path."""
    monkeypatch.setenv("APP_BASE_PATH", "/tg")
    tmp_dir = tempfile.mkdtemp()
    config = AppConfig(
        base_path="/tg",
        session_dir=Path(tmp_dir),
    )
    app = create_app(config)
    with TestClient(app) as client:
        yield client
    # Cleanup: remove session dir
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


class TestBasePath:
    """PLAN_AUDIT §19.2 п.10: работа с APP_BASE_PATH=/tg."""

    def test_base_path_routing(self, client_with_base_path: TestClient):
        """All routes respect the /tg base path prefix."""
        # Index page at /tg/
        resp = client_with_base_path.get("/tg/")
        assert resp.status_code == 200

        # Upload endpoint at /tg/upload/thermograms
        csv = b"temp;deltatemp;time;mass\n25.0;0.0;0.0;100.0\n100.0;5.0;7.5;99.5\n"
        resp = client_with_base_path.post(
            "/tg/upload/thermograms",
            files={"thermograms": ("test.dat", csv, "text/plain")},
        )
        assert resp.status_code == 200

        # Process at /tg/process
        resp = client_with_base_path.post("/tg/process")
        assert resp.status_code == 200

        # Effect at /tg/effect
        resp = client_with_base_path.post("/tg/effect", data={"xmin": "50", "xmax": "150"})
        assert resp.status_code == 200

        # Export session at /tg/export/session
        resp = client_with_base_path.get("/tg/export/session")
        assert resp.status_code == 200