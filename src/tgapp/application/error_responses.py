"""User-facing error messages per PLAN_AUDIT §18.

All error messages are in Russian, user-visible, never expose internal paths
or tracebacks.  Errors carry a severity (info / warning / error) and optional
recovery details (row counts, ranges, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ErrorSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class UserError:
    """User-facing error message."""

    message: str
    severity: ErrorSeverity
    details: Optional[str] = None  # Recovery info (row counts, ranges, etc.)

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "severity": self.severity.value,
            "details": self.details,
        }


# ---------------------------------------------------------------------------
# Factory functions — domain-exception → UserError mapping
# ---------------------------------------------------------------------------


def file_not_recognized(filename: str) -> UserError:
    return UserError(
        message=f"Файл '{filename}' не распознан: невозможно определить формат.",
        severity=ErrorSeverity.ERROR,
        details="Поддерживаемые форматы: CSV, TSV, разделённые точкой с запятой или пробелами.",
    )


def missing_column(column: str) -> UserError:
    return UserError(
        message=f"Отсутствует колонка '{column}' в данных.",
        severity=ErrorSeverity.ERROR,
        details="Ожидаемые колонки: temp, time, mass, deltatemp.",
    )


def insufficient_points(n: int, required: int = 3) -> UserError:
    return UserError(
        message=f"Недостаточно точек: {n} < {required}.",
        severity=ErrorSeverity.ERROR,
        details="Минимальное количество точек для обработки: 3.",
    )


def non_monotonic_time() -> UserError:
    return UserError(
        message="Время не монотонно (обратное движение).",
        severity=ErrorSeverity.ERROR,
        details="Температура должна возрастать или убывать непрерывно.",
    )


def non_monotonic_temp() -> UserError:
    return UserError(
        message="Температура не монотонна (обратное движение).",
        severity=ErrorSeverity.ERROR,
        details="Температура должна возрастать или убывать непрерывно.",
    )


def no_common_range() -> UserError:
    return UserError(
        message="Нет общего температурного диапазона для файлов.",
        severity=ErrorSeverity.ERROR,
        details="Каждый файл должен иметь хотя бы частично пересекающийся диапазон температур.",
    )


def correction_coverage_error(min_temp: float, max_temp: float, corr_min: float, corr_max: float) -> UserError:
    return UserError(
        message=f"Correction-файл не покрывает диапазон [{min_temp:.1f}, {max_temp:.1f}].",
        severity=ErrorSeverity.ERROR,
        details=f"Correction данные доступны только в диапазоне [{corr_min:.1f}, {corr_max:.1f}].",
    )


def invalid_smoothing_params(window: int, polyorder: int) -> UserError:
    return UserError(
        message=f"Неверные параметры сглаживания: window={window}, polyorder={polyorder}.",
        severity=ErrorSeverity.ERROR,
        details="polyorder должен быть меньше window.",
    )


def non_positive_mass(mass: float) -> UserError:
    return UserError(
        message=f"Начальная масса неположительна: {mass} г.",
        severity=ErrorSeverity.ERROR,
        details="Масса должна быть строго положительной.",
    )


def archive_corrupted(filename: str) -> UserError:
    return UserError(
        message=f"Архив '{filename}' повреждён или не может быть распакован.",
        severity=ErrorSeverity.ERROR,
        details="Проверьте целостность файла и попробуйте снова.",
    )


def archive_size_limit(exceeded: int, limit: int) -> UserError:
    return UserError(
        message=f"Архив превышает лимит: {exceeded} байт > {limit} байт.",
        severity=ErrorSeverity.ERROR,
        details="Максимальный размер архива ограничен для безопасности.",
    )


def generic_error(details: str | None = None) -> UserError:
    """Catch-all for unexpected failures — never exposes internals."""
    return UserError(
        message="Произошла ошибка при обработке.",
        severity=ErrorSeverity.ERROR,
        details=details or "Проверьте данные и параметры, затем повторите попытку.",
    )


def recovery_warning(
    rows_removed: int,
    rows_interpolated: int,
    actual_range: tuple[float, float],
    narrowed_range: Optional[tuple[float, float]] = None,
) -> UserError:
    """Recovery warning with data recovery details."""
    parts = [f"Восстановлено: удалено {rows_removed} строк, интерполировано {rows_interpolated} точек."]
    parts.append(f"Рабочий диапазон: [{actual_range[0]:.1f}, {actual_range[1]:.1f}] °C.")
    if narrowed_range:
        parts.append(f"Сужение диапазона: [{narrowed_range[0]:.1f}, {narrowed_range[1]:.1f}] °C.")
    return UserError(
        message="\n".join(parts),
        severity=ErrorSeverity.WARNING,
    )