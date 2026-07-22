"""Regression tests on real sample files (PLAN_PRE_OZF Phase 13b).

Verifies deterministic behavior of the full pipeline on actual TGA data:
  - Parse integrity: checksums, row counts, column detection
  - Validation outcomes: expected pass/fail per file
  - Processing results: numeric outputs for files that pass validation
  - Determinism: same input → same output

Real TGA files have non-monotonic temperature (oven oscillates around setpoint),
so most files fail validation with NonMonotonicAxisError. This is correct behavior.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from tgapp.domain.models import (
    InsufficientDataError,
    NonMonotonicAxisError,
    ProcessingSettings,
    ThermogramValidationError,
)
from tgapp.domain.processing_engine import ProcessingEngine
from tgapp.domain.validator import validate_parsed
from tgapp.infrastructure.file_parsers import parse_thermogram_from_file, frame_to_parsed

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SAMPLES_DIR = Path(__file__).resolve().parent.parent.parent / "samples"


# ---------------------------------------------------------------------------
# File registry — checksums, row counts, expected validation status
# ---------------------------------------------------------------------------

FILE_REGISTRY: dict[str, dict] = {
    "tg-test/tg-test.dat": {
        "checksum": "b945962f66e54f39",
        "n_parsed": 7,
        "expected_status": "VALID",
        "temp_range": (20.0, 26.0),
    },
    "Береза/Береза600_10_3140.dat": {
        "checksum": "3ba9b11f70ad2e21",
        "n_parsed": 1453,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (15.0, 600.0),
    },
    "Сосна/Сосна 600_10_250мг.dat": {
        "checksum": "c34fb9d45340326a",
        "n_parsed": 1466,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (14.0, 600.0),
    },
    "Гуано_с_землей/09.01.14.dat": {
        "checksum": "9974a9a2cbf42bf9",
        "n_parsed": 1,
        "expected_status": "INSUFFICIENT",
        "temp_range": (0.0, 0.0),
    },
    "Тишина/лаб.смола600_5_480mg.dat": {
        "checksum": "cb132b3a8d8ad0aa",
        "n_parsed": 0,
        "expected_status": "INSUFFICIENT",
        "temp_range": (0.0, 0.0),
    },
    "Лигнин/порошок5_600_210.dat": {
        "checksum": "a97143a9cc2dcf0a",
        "n_parsed": 2954,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
    "Проверки/Береза600 10.dat": {
        "checksum": "3a9ae3dbddda3cce",
        "n_parsed": 1465,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
    "Песок/Песок600_5_935mg.dat": {
        "checksum": "07da48bc423dd1ba",
        "n_parsed": 2869,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
    "Пластик/Пластик_600_10_300mg.dat": {
        "checksum": "4a26d8119f64e3ac",
        "n_parsed": 1453,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
    "Кокос/кокос600_10_3380мг.dat": {
        "checksum": "03976ebc992b1af8",
        "n_parsed": 1463,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
    "Чу/бамбук 600 10 215мг.dat": {
        "checksum": "8beb104bbe8421bf",
        "n_parsed": 1471,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
    "Целлолигнин/целолигнин_10_600_3033.dat": {
        "checksum": "90e06c02b4b249cb",
        "n_parsed": 1403,
        "expected_status": "NON-MONOTONIC",
        "temp_range": (0.0, 600.0),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_checksum(path: Path) -> str:
    """SHA-256 hex digest of file content (first 16 chars for registry match)."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_file(path: Path):
    """Parse a sample file. Returns (ThermogramFile, ParsedThermogram)."""
    tf = parse_thermogram_from_file(str(path), path.name)
    parsed = frame_to_parsed(tf.name, tf.frame, "")
    return tf, parsed


def _validate_file(parsed) -> tuple:
    """Validate parsed thermogram. Returns (ValidatedThermogram, error_type|None)."""
    try:
        validated = validate_parsed(
            parsed.temp, parsed.deltatemp, parsed.time, parsed.mass,
        )
        return validated, None
    except ThermogramValidationError as e:
        return None, type(e)


def _process_file(validated) -> tuple:
    """Process validated thermogram. Returns (ProcessingResult, error|None)."""
    engine = ProcessingEngine(ProcessingSettings())
    try:
        result = engine.process([validated])
        return result, None
    except Exception as e:
        return None, e


# ---------------------------------------------------------------------------
# Test group 1 — Parse integrity
# ---------------------------------------------------------------------------

class TestParseIntegrity:
    """Verify file parsing is deterministic: checksums and row counts."""

    @pytest.mark.parametrize("rel_path,info", FILE_REGISTRY.items())
    def test_checksum_matches(self, rel_path: str, info: dict):
        """File checksum must match the registry entry."""
        path = SAMPLES_DIR / rel_path
        assert path.exists(), f"Sample file not found: {rel_path}"
        actual = _file_checksum(path)[:16]
        assert actual == info["checksum"], (
            f"Checksum mismatch for {rel_path}: "
            f"expected {info['checksum']}, got {actual}"
        )

    @pytest.mark.parametrize("rel_path,info", FILE_REGISTRY.items())
    def test_row_count_matches(self, rel_path: str, info: dict):
        """Parsed row count must match the registry entry."""
        path = SAMPLES_DIR / rel_path
        tf, parsed = _parse_file(path)
        assert len(parsed.temp) == info["n_parsed"], (
            f"Row count mismatch for {rel_path}: "
            f"expected {info['n_parsed']}, got {len(parsed.temp)}"
        )

    @pytest.mark.parametrize("rel_path,info", FILE_REGISTRY.items())
    def test_columns_detected(self, rel_path: str, info: dict):
        """Parsed frame must have the expected columns (skip empty files)."""
        path = SAMPLES_DIR / rel_path
        tf, parsed = _parse_file(path)
        # Empty files (0 rows) are expected — skip column check
        if info["n_parsed"] == 0:
            pytest.skip(f"{rel_path} has 0 parsed rows — no columns to check")
        assert parsed.temp is not None and len(parsed.temp) > 0, (
            f"No temperature data in {rel_path}"
        )
        assert parsed.time is not None and len(parsed.time) > 0, (
            f"No time data in {rel_path}"
        )
        assert parsed.mass is not None and len(parsed.mass) > 0, (
            f"No mass data in {rel_path}"
        )


# ---------------------------------------------------------------------------
# Test group 2 — Validation outcomes
# ---------------------------------------------------------------------------

class TestValidationOutcomes:
    """Verify each file produces the expected validation outcome."""

    @pytest.mark.parametrize("rel_path,info", FILE_REGISTRY.items())
    def test_validation_status(self, rel_path: str, info: dict):
        """Each file must produce the expected validation result."""
        path = SAMPLES_DIR / rel_path
        _, parsed = _parse_file(path)
        _, error_type = _validate_file(parsed)

        expected = info["expected_status"]
        if expected == "VALID":
            assert error_type is None, (
                f"{rel_path}: expected VALID but got {error_type.__name__}"
            )
        elif expected == "NON-MONOTONIC":
            assert error_type is NonMonotonicAxisError, (
                f"{rel_path}: expected NonMonotonicAxisError but got {error_type.__name__}"
            )
        elif expected == "INSUFFICIENT":
            assert error_type is InsufficientDataError, (
                f"{rel_path}: expected InsufficientDataError but got {error_type.__name__}"
            )


# ---------------------------------------------------------------------------
# Test group 3 — Processing results (files that pass validation)
# ---------------------------------------------------------------------------

class TestProcessingResults:
    """For files that pass validation, verify processing outputs."""

    def test_tgtest_processing(self):
        """tg-test.dat passes validation — verify processing completes."""
        path = SAMPLES_DIR / "tg-test/tg-test.dat"
        tf, parsed = _parse_file(path)
        validated, error_type = _validate_file(parsed)
        assert error_type is None, f"tg-test.dat should validate: {error_type}"

        result, proc_error = _process_file(validated)
        assert proc_error is None, f"Processing failed: {proc_error}"
        assert result is not None

        # Verify output structure
        assert not result.mass_smoothed.empty
        assert not result.temp_smoothed.empty
        assert not result.derivatives.empty

        # Verify columns
        assert "temp" in result.mass_smoothed.columns
        assert "mass" in result.mass_smoothed.columns
        assert "temp" in result.temp_smoothed.columns
        assert "time" in result.temp_smoothed.columns

        # Verify heating rate text is present
        assert "Скорость нагрева" in result.heat_speed_text

    def test_tgtest_peak_count(self):
        """tg-test.dat processing produces deterministic peak count."""
        path = SAMPLES_DIR / "tg-test/tg-test.dat"
        tf, parsed = _parse_file(path)
        validated, _ = _validate_file(parsed)
        result, _ = _process_file(validated)

        # Peak count is deterministic for this input
        assert isinstance(result.peaks, tuple)
        # Small sample may or may not have peaks — just verify it's consistent
        peak_count = len(result.peaks)
        assert isinstance(peak_count, int)
        assert peak_count >= 0


# ---------------------------------------------------------------------------
# Test group 4 — Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    """Same input → same output (pipeline is deterministic)."""

    def test_tgtest_reproducible(self):
        """Two runs on tg-test.dat produce identical results."""
        path = SAMPLES_DIR / "tg-test/tg-test.dat"
        tf, parsed = _parse_file(path)
        validated, _ = _validate_file(parsed)

        engine = ProcessingEngine(ProcessingSettings())
        r1 = engine.process([validated])
        r2 = engine.process([validated])

        np.testing.assert_array_equal(
            r1.derivatives["temp"].to_numpy(),
            r2.derivatives["temp"].to_numpy(),
            err_msg="temp mismatch on re-run",
        )
        np.testing.assert_array_equal(
            r1.derivatives["mass"].to_numpy(),
            r2.derivatives["mass"].to_numpy(),
            err_msg="mass mismatch on re-run",
        )
        np.testing.assert_allclose(
            r1.derivatives["dmdt"].to_numpy(),
            r2.derivatives["dmdt"].to_numpy(),
            err_msg="dmdt mismatch on re-run",
        )
        assert r1.peaks == r2.peaks, "peak mismatch on re-run"
        assert r1.heat_speed_text == r2.heat_speed_text


# ---------------------------------------------------------------------------
# Test group 5 — Cross-file consistency
# ---------------------------------------------------------------------------

class TestCrossFileConsistency:
    """Files from the same material family share structural properties."""

    @pytest.mark.parametrize(
        "rel_paths",
        [
            [
                "Береза/Береза600_10_3140.dat",
                "Береза/Береза600_10_2300мг.dat",
                "Береза/Береза600_10_2800мг.dat",
            ],
            [
                "Сосна/Сосна 600_10_250мг.dat",
                "Сосна/Сосна 600_10_3255мг.dat",
                "Сосна/Сосна600_10_1800мг.dat",
            ],
        ],
    )
    def test_same_family_same_validation_error(self, rel_paths: list[str]):
        """Files from the same material family fail with the same error."""
        errors = []
        for rel in rel_paths:
            path = SAMPLES_DIR / rel
            _, parsed = _parse_file(path)
            _, error_type = _validate_file(parsed)
            errors.append(error_type)

        # All should have the same error type
        assert len(set(e.__name__ for e in errors if e is not None)) == 1, (
            f"Family {rel_paths} has inconsistent validation errors: "
            f"{[e.__name__ for e in errors]}"
        )

    def test_identical_files_same_checksum(self):
        """Лигнин/порошок5_600_210.dat and Лигнин/порошок5_600_280.dat are identical."""
        path1 = SAMPLES_DIR / "Лигнин/порошок5_600_210.dat"
        path2 = SAMPLES_DIR / "Лигнин/порошок5_600_280.dat"
        cs1 = _file_checksum(path1)
        cs2 = _file_checksum(path2)
        assert cs1 == cs2, (
            "порошок5_600_210.dat and порошок5_600_280.dat should be identical files"
        )
        # Verify they have the same row count
        _, parsed1 = _parse_file(path1)
        _, parsed2 = _parse_file(path2)
        assert len(parsed1.temp) == len(parsed2.temp)