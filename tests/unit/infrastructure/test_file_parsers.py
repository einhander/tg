"""Tests for tgapp.infrastructure.file_parsers."""

from __future__ import annotations

import pandas as pd
import pytest

from tgapp.application.dto import UploadPayload
from tgapp.infrastructure.file_parsers import (
    _read_frame,
    decode_dash_upload,
    parse_thermogram_uploads,
)


class TestReadFrame:
    """_read_frame parsing behavior."""

    def test_csv_semicolon_separator(self):
        """CSV with ; separator → 4 columns."""
        csv_data = "temp;deltatemp;time;mass\n15.0;0.5;0.04;100.0\n16.0;0.6;0.08;99.5"
        result = _read_frame(csv_data.encode("utf-8"))
        assert len(result) == 2
        assert len(result.columns) == 4

    def test_csv_comma_separator(self):
        """CSV with , separator → 4 columns."""
        csv_data = "temp,deltatemp,time,mass\n15.0,0.5,0.04,100.0\n16.0,0.6,0.08,99.5"
        result = _read_frame(csv_data.encode("utf-8"))
        assert len(result) == 2
        assert len(result.columns) == 4

    def test_empty_bytes(self):
        """Empty bytes → empty DataFrame with correct columns."""
        result = _read_frame(b"")
        assert result.empty
        assert list(result.columns) == ["temp", "deltatemp", "time", "mass"]

    def test_tab_separator(self):
        """Tab-separated data → parsed."""
        data = "15.0\t0.5\t0.04\t100.0\n16.0\t0.6\t0.08\t99.5"
        result = _read_frame(data.encode("utf-8"))
        # Tab separator is tried first and works, but header=infer means
        # first row becomes header → 1 data row
        assert len(result.columns) == 4

    def test_unparseable_returns_empty(self):
        """Completely unparseable content → empty DataFrame."""
        # Use content that fails all separator attempts
        result = _read_frame(b"\x00\x01\x02\x03\x04\x05")
        assert result.empty


class TestDecodeDashUpload:
    """decode_dash_upload."""

    def test_base64_content(self):
        """Base64-encoded content (Dash format) → decoded bytes."""
        import base64
        original = b"hello world"
        encoded = base64.b64encode(original).decode("ascii")
        # Dash format: "data:<type>;base64,<encoded>"
        content = f"data:text/plain;base64,{encoded}"
        upload = UploadPayload(filename="test.txt", content_type="text/plain", content=content)
        result = decode_dash_upload(upload)
        assert result.raw_bytes == original
        assert result.filename == "test.txt"

    def test_empty_content(self):
        """No content → empty bytes."""
        upload = UploadPayload(filename="empty.dat")
        result = decode_dash_upload(upload)
        assert result.raw_bytes == b""


class TestParseThermogramUploads:
    """parse_thermogram_uploads."""

    def test_csv_upload(self):
        """CSV upload → ThermogramFile with parsed frame."""
        import base64
        csv_data = "temp;deltatemp;time;mass\n15.0;0.5;0.04;100.0\n16.0;0.6;0.08;99.5"
        encoded = base64.b64encode(csv_data.encode("utf-8")).decode("ascii")
        # Dash format: "data:<type>;base64,<encoded>"
        content = f"data:text/plain;base64,{encoded}"
        upload = UploadPayload(filename="test.dat", content_type="text/plain", content=content)
        result = parse_thermogram_uploads([upload])
        assert len(result) == 1
        assert result[0].name == "test.dat"
        assert len(result[0].frame) == 2
        assert "temp" in list(result[0].frame.columns)

    def test_empty_content(self):
        """Empty upload → ThermogramFile with empty frame."""
        upload = UploadPayload(filename="empty.dat")
        result = parse_thermogram_uploads([upload])
        assert len(result) == 1
        assert result[0].frame.empty

    def test_multiple_uploads(self):
        """Multiple uploads → multiple ThermogramFiles."""
        import base64
        csv1 = "temp;deltatemp;time;mass\n15.0;0.5;0.0;100.0"
        csv2 = "temp;deltatemp;time;mass\n20.0;0.3;0.0;200.0"
        uploads = [
            UploadPayload(filename="file1.dat", content=f"data:text/plain;base64,{base64.b64encode(csv1.encode()).decode()}"),
            UploadPayload(filename="file2.dat", content=f"data:text/plain;base64,{base64.b64encode(csv2.encode()).decode()}"),
        ]
        result = parse_thermogram_uploads(uploads)
        assert len(result) == 2
        assert result[0].name == "file1.dat"
        assert result[1].name == "file2.dat"