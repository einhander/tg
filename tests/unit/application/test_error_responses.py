"""Tests for user-facing error responses (PLAN_AUDIT §18)."""

from __future__ import annotations

import numpy as np
import pytest

from tgapp.application.error_responses import (
    ErrorSeverity,
    UserError,
    archive_corrupted,
    archive_size_limit,
    correction_coverage_error,
    file_not_recognized,
    generic_error,
    insufficient_points,
    invalid_smoothing_params,
    missing_column,
    no_common_range,
    non_monotonic_temp,
    non_monotonic_time,
    non_positive_mass,
    recovery_warning,
)
from tgapp.domain.models import (
    InsufficientDataError,
    NonMonotonicAxisError,
    ThermogramValidationError,
)


# ---------------------------------------------------------------------------
# Unit tests for factory functions
# ---------------------------------------------------------------------------


class TestFileNotRecognized:
    def test_correct_message_format(self):
        err = file_not_recognized("test.dat")
        assert "test.dat" in err.message
        assert "не распознан" in err.message
        assert err.severity == ErrorSeverity.ERROR
        assert "CSV" in err.details

    def test_to_dict(self):
        err = file_not_recognized("test.dat")
        d = err.to_dict()
        assert d["message"] == err.message
        assert d["severity"] == "error"
        assert d["details"] == err.details


class TestInsufficientPoints:
    def test_correct_message_format(self):
        err = insufficient_points(2)
        assert "2" in err.message
        assert "3" in err.message
        assert err.severity == ErrorSeverity.ERROR

    def test_custom_required(self):
        err = insufficient_points(5, required=10)
        assert "5" in err.message
        assert "10" in err.message


class TestNonMonotonic:
    def test_non_monotonic_time(self):
        err = non_monotonic_time()
        assert "Время" in err.message
        assert "монотонно" in err.message
        assert err.severity == ErrorSeverity.ERROR

    def test_non_monotonic_temp(self):
        err = non_monotonic_temp()
        assert "Температура" in err.message
        assert "монотонна" in err.message
        assert err.severity == ErrorSeverity.ERROR


class TestNoCommonRange:
    def test_message(self):
        err = no_common_range()
        assert "Нет общего" in err.message
        assert "диапазона" in err.message
        assert err.severity == ErrorSeverity.ERROR


class TestCorrectionCoverageError:
    def test_message_with_ranges(self):
        err = correction_coverage_error(100.0, 500.0, 150.0, 450.0)
        assert "[100.0, 500.0]" in err.message
        assert "[150.0, 450.0]" in err.details
        assert err.severity == ErrorSeverity.ERROR


class TestInvalidSmoothingParams:
    def test_message(self):
        err = invalid_smoothing_params(3, 5)
        assert "window=3" in err.message
        assert "polyorder=5" in err.message
        assert err.severity == ErrorSeverity.ERROR


class TestNonPositiveMass:
    def test_message(self):
        err = non_positive_mass(0.0)
        assert "0.0" in err.message
        assert "неположительна" in err.message
        assert err.severity == ErrorSeverity.ERROR

    def test_negative_mass(self):
        err = non_positive_mass(-1.5)
        assert "-1.5" in err.message


class TestArchiveErrors:
    def test_archive_corrupted(self):
        err = archive_corrupted("session.tg")
        assert "session.tg" in err.message
        assert "повреждён" in err.message
        assert err.severity == ErrorSeverity.ERROR

    def test_archive_size_limit(self):
        err = archive_size_limit(100_000_000, 50_000_000)
        assert "100000000" in err.message
        assert "50000000" in err.message
        assert err.severity == ErrorSeverity.ERROR


class TestGenericError:
    def test_default_details(self):
        err = generic_error()
        assert "ошибка" in err.message.lower()
        assert err.details is not None

    def test_custom_details(self):
        err = generic_error("custom detail")
        assert err.details == "custom detail"


class TestRecoveryWarning:
    def test_includes_row_counts_and_ranges(self):
        err = recovery_warning(
            rows_removed=10,
            rows_interpolated=5,
            actual_range=(100.0, 500.0),
        )
        assert "10" in err.message
        assert "5" in err.message
        assert "[100.0, 500.0]" in err.message
        assert err.severity == ErrorSeverity.WARNING

    def test_with_narrowed_range(self):
        err = recovery_warning(
            rows_removed=3,
            rows_interpolated=1,
            actual_range=(100.0, 500.0),
            narrowed_range=(150.0, 450.0),
        )
        assert "150.0" in err.message
        assert "450.0" in err.message
        assert "Сужение" in err.message

    def test_to_dict(self):
        err = recovery_warning(5, 2, (100.0, 300.0))
        d = err.to_dict()
        assert d["severity"] == "warning"
        assert "5" in d["message"]


class TestErrorSeverityLevels:
    def test_info_level(self):
        err = UserError("info msg", ErrorSeverity.INFO)
        assert err.severity == ErrorSeverity.INFO
        assert err.to_dict()["severity"] == "info"

    def test_warning_level(self):
        err = UserError("warn msg", ErrorSeverity.WARNING)
        assert err.severity == ErrorSeverity.WARNING
        assert err.to_dict()["severity"] == "warning"

    def test_error_level(self):
        err = UserError("error msg", ErrorSeverity.ERROR)
        assert err.severity == ErrorSeverity.ERROR
        assert err.to_dict()["severity"] == "error"


class TestUserErrorToDict:
    def test_serializes_correctly(self):
        err = UserError("test", ErrorSeverity.ERROR, "details here")
        d = err.to_dict()
        assert d == {
            "message": "test",
            "severity": "error",
            "details": "details here",
        }

    def test_serializes_without_details(self):
        err = UserError("test", ErrorSeverity.INFO)
        d = err.to_dict()
        assert d == {
            "message": "test",
            "severity": "info",
            "details": None,
        }


# ---------------------------------------------------------------------------
# Integration tests: domain exceptions → UserError mapping
# ---------------------------------------------------------------------------


class TestDomainExceptionMapping:
    def test_insufficient_data_error_mapping(self):
        """InsufficientDataError → insufficient_points UserError."""
        try:
            raise InsufficientDataError("test")
        except InsufficientDataError:
            err = insufficient_points(2)
            assert "Недостаточно точек" in err.message

    def test_non_monotonic_axis_error_mapping_time(self):
        """NonMonotonicAxisError with time → non_monotonic_time."""
        try:
            raise NonMonotonicAxisError("Время не монотонно")
        except NonMonotonicAxisError as e:
            msg = str(e).lower()
            if "время" in msg or "time" in msg:
                err = non_monotonic_time()
            else:
                err = non_monotonic_temp()
            assert "Время" in err.message

    def test_non_monotonic_axis_error_mapping_temp(self):
        """NonMonotonicAxisError with temp → non_monotonic_temp."""
        try:
            raise NonMonotonicAxisError("Температура не монотонна")
        except NonMonotonicAxisError as e:
            msg = str(e).lower()
            if "время" in msg or "time" in msg:
                err = non_monotonic_time()
            else:
                err = non_monotonic_temp()
            assert "Температура" in err.message

    def test_thermogram_validation_error_becomes_user_error(self):
        """ThermogramValidationError → UserError with same message."""
        try:
            raise ThermogramValidationError("custom error message")
        except ThermogramValidationError as e:
            err = UserError(message=str(e), severity=ErrorSeverity.ERROR)
            assert err.message == "custom error message"
            assert err.severity == ErrorSeverity.ERROR