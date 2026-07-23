class KineticError(Exception):
    """Базовое исключение кинетики."""


class KineticValidationError(KineticError):
    """Ошибка валидации кинетических данных."""


class InsufficientRunsError(KineticValidationError):
    """Недостаточно опытов для изоконверсионного анализа."""


class IdenticalHeatingRatesError(KineticValidationError):
    """Одинаковые скорости нагрева в исследовании."""


class ConversionCalculationError(KineticValidationError):
    """Ошибка расчёта степени превращения."""


class InterpolationError(KineticValidationError):
    """Ошибка интерполяции."""


class RegressionError(KineticError):
    """Ошибка линейной регрессии."""


class PlateauNotFoundError(KineticValidationError):
    """Не найдено плато для определения m0/mf."""


class HeatingProgramError(KineticValidationError):
    """Ошибка расчёта программы нагрева."""