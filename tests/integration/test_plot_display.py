"""Regression tests for plot display — trace data integrity (PLAN_PRE_OZF §19.3).

Verifies that the POST /process response contains a valid Plotly figure JSON
embedded in the HTML, with non-empty x/y arrays in every trace.
"""

from __future__ import annotations

import html
import json
import re
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tgapp.config import AppConfig
from tgapp.web.app import create_app

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """TestClient with debug=True so session cookies are not marked secure.

    The default ``conftest.py::client`` uses ``create_app()`` which reads
    ``APP_DEBUG`` from env.  When debug is ``False`` the session cookie gets
    ``secure=True`` and the TestClient (HTTP, not HTTPS) refuses to send it
    on subsequent requests — causing every request after the first to create
    a fresh session with no uploaded data.
    """
    tmp_dir = tempfile.mkdtemp()
    config = AppConfig(debug=True, session_dir=Path(tmp_dir))
    app = create_app(config)
    with TestClient(app) as c:
        yield c
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def sample_birza_2800_path() -> Path:
    """Path to the Береза 2800mg sample thermogram file."""
    p = Path(__file__).resolve().parent.parent.parent / "samples" / "Береза" / "Береза600_10_2800мг.dat"
    assert p.exists(), f"Sample file missing: {p}"
    return p


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_plot_json(html_text: str) -> dict:
    """Extract and parse plot JSON from the ``data-plot-json`` attribute.

    The HTML contains a div like::

        <div class="main-plot" data-plot-json='{{ escaped_json }}' ...>

    The JSON is HTML-escaped by Jinja ``|e``. We extract the attribute value,
    unescape it, and parse as JSON.
    """
    # Match data-plot-json='...' — attribute value is HTML-escaped JSON.
    # Use a greedy match up to the closing quote; the value may contain
    # escaped quotes like &#39; or &quot; from Jinja's escape filter.
    match = re.search(r'data-plot-json=[\'"]([^\'"]+)[\'"]', html_text)
    assert match is not None, (
        "No data-plot-json attribute found in process response. "
        "Response snippet:\n" + html_text[:500]
    )
    escaped_json = match.group(1)
    unescaped = html.unescape(escaped_json)
    return json.loads(unescaped)


# ---------------------------------------------------------------------------
# Test class: plot data traces
# ---------------------------------------------------------------------------


class TestPlotDisplayRegression:
    """Verify plot JSON has proper trace data after upload + process."""

    def _full_flow(self, client: TestClient, dat_path: Path) -> dict:
        """Upload a thermogram, run processing, extract plot JSON."""
        data = dat_path.read_bytes()
        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", data, "text/plain")},
            follow_redirects=False,
        )
        resp = client.post("/process", follow_redirects=True)
        assert resp.status_code == 200, (
            f"POST /process returned {resp.status_code}. "
            f"Response snippet:\n{resp.text[:500]}"
        )
        return _extract_plot_json(resp.text)

    def test_plot_has_data_traces(self, client: TestClient, sample_birza_path: Path):
        """Plot JSON must contain a non-empty ``data`` array with traces that have x/y arrays."""
        plot = self._full_flow(client, sample_birza_path)

        data = plot.get("data", [])
        assert isinstance(data, list), "Plot 'data' must be a list"
        assert len(data) >= 3, (
            f"Expected at least 3 traces (TG, DTA, DTG), got {len(data)}. "
            f"Full data keys: {list(plot.keys())}"
        )

        for i, trace in enumerate(data):
            assert "x" in trace, f"Trace {i} missing 'x' key"
            assert "y" in trace, f"Trace {i} missing 'y' key"
            assert isinstance(trace["x"], list), f"Trace {i} 'x' must be a list"
            assert isinstance(trace["y"], list), f"Trace {i} 'y' must be a list"
            assert len(trace["x"]) > 0, f"Trace {i} 'x' array is empty"
            assert len(trace["y"]) > 0, f"Trace {i} 'y' array is empty"

    def test_plot_has_tg_trace(self, client: TestClient, sample_birza_path: Path):
        """At least one trace must have a name containing 'ТГ'."""
        plot = self._full_flow(client, sample_birza_path)
        names = [t.get("name", "") for t in plot.get("data", [])]
        assert any("ТГ" in name for name in names), (
            f"No trace with 'ТГ' in name. Found names: {names}"
        )

    def test_plot_has_dta_trace(self, client: TestClient, sample_birza_path: Path):
        """At least one trace must have a name containing 'ДТА'."""
        plot = self._full_flow(client, sample_birza_path)
        names = [t.get("name", "") for t in plot.get("data", [])]
        assert any("ДТА" in name for name in names), (
            f"No trace with 'ДТА' in name. Found names: {names}"
        )

    def test_plot_has_dtg_trace(self, client: TestClient, sample_birza_path: Path):
        """At least one trace must have a name containing 'ТГП'."""
        plot = self._full_flow(client, sample_birza_path)
        names = [t.get("name", "") for t in plot.get("data", [])]
        assert any("ТГП" in name for name in names), (
            f"No trace with 'ТГП' in name. Found names: {names}"
        )


# ---------------------------------------------------------------------------
# Test class: Береза 2800mg file
# ---------------------------------------------------------------------------


class TestPlotBirza2800:
    """Same plot assertions on the Береза 2800mg file."""

    def test_plot_birza_2800(self, client: TestClient, sample_birza_2800_path: Path):
        """Plot JSON from Береза600_10_2800мг.dat has data traces with x/y arrays."""
        plot = self._full_flow(client, sample_birza_2800_path)

        data = plot.get("data", [])
        assert len(data) >= 3, f"Expected >= 3 traces, got {len(data)}"

        for i, trace in enumerate(data):
            assert "x" in trace and "y" in trace
            assert len(trace["x"]) > 0 and len(trace["y"]) > 0

        names = [t.get("name", "") for t in data]
        assert any("ТГ" in n for n in names), f"No ТГ trace. Names: {names}"
        assert any("ДТА" in n for n in names), f"No ДТА trace. Names: {names}"
        assert any("ТГП" in n for n in names), f"No ТГП trace. Names: {names}"

    def _full_flow(self, client: TestClient, dat_path: Path) -> dict:
        """Upload + process → extract plot JSON."""
        data = dat_path.read_bytes()
        client.post(
            "/upload/thermograms",
            files={"thermograms": ("test.dat", data, "text/plain")},
            follow_redirects=False,
        )
        resp = client.post("/process", follow_redirects=True)
        assert resp.status_code == 200
        return _extract_plot_json(resp.text)