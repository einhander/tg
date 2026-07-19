"""Route-level integration tests for FastAPI endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

import pytest


class TestRoutes:
    """Test HTTP routes via TestClient."""

    def test_index_page(self, client: TestClient):
        """GET / → 200, page contains 'Термограмма'."""
        r = client.get("/")
        assert r.status_code == 200
        assert "Термограмма" in r.text

    def test_upload_missing_field(self, client: TestClient):
        """POST /upload/thermograms without file → 422."""
        r = client.post("/upload/thermograms", data={})
        assert r.status_code == 422

    def test_upload_thermogram_csv(self, client: TestClient):
        """POST /upload/thermograms with CSV file → 200, session created."""
        csv_content = (
            b"temp;deltatemp;time;mass\n"
            b"25.0;0.0;0.0;100.0\n"
            b"100.0;5.0;7.5;99.5\n"
            b"200.0;-3.0;17.5;98.0\n"
        )
        r = client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", csv_content, "text/plain")},
        )
        assert r.status_code == 200
        assert "Loaded 1 thermogram file" in r.text

    def test_process_without_thermogram(self, client: TestClient):
        """POST /process with no thermograms → 200 (graceful, not crash)."""
        r = client.post("/process")
        assert r.status_code == 200

    def test_process_with_valid_settings(self, client: TestClient):
        """POST /process with valid Form settings → 200."""
        csv_content = (
            b"temp;deltatemp;time;mass\n"
            b"25.0;0.0;0.0;100.0\n"
            b"100.0;5.0;7.5;99.5\n"
            b"200.0;-3.0;17.5;98.0\n"
        )
        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", csv_content, "text/plain")},
        )
        r = client.post("/process", data={
            "peak_prominence_sigma": "2.0",
            "sg_mode": "false",
        })
        assert r.status_code == 200

    def test_upload_correction(self, client: TestClient):
        """POST /upload/correction with file → 200."""
        csv_content = (
            b"temp;deltatemp;time;mass\n"
            b"25.0;0.0;0.0;100.0\n"
            b"100.0;1.0;7.5;99.5\n"
        )
        r = client.post(
            "/upload/correction",
            files={"correction": ("correction.dat", csv_content, "text/plain")},
        )
        assert r.status_code == 200
        assert "Loaded correction file" in r.text

    def test_effect_endpoint(self, client: TestClient):
        """POST /effect with xmin/xmax → 200."""
        r = client.post("/effect", data={"xmin": "50.0", "xmax": "150.0"})
        assert r.status_code == 200