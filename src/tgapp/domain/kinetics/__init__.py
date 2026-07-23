from tgapp.domain.kinetics.constants import GAS_CONSTANT_J_MOL_K, OFW_DOYLE_SLOPE_FACTOR
from tgapp.domain.kinetics.errors import (
    KineticError,
    KineticValidationError,
    InsufficientRunsError,
    IdenticalHeatingRatesError,
    ConversionCalculationError,
    InterpolationError,
    RegressionError,
    PlateauNotFoundError,
    HeatingProgramError,
)
from tgapp.domain.kinetics.methods.base import BaseKineticMethod
from tgapp.domain.kinetics.methods.ofw import OzawaFlynnWallMethod
from tgapp.domain.kinetics.methods.kas import KissingerAkahiraSunoseMethod
from tgapp.domain.kinetics.methods.friedman import FriedmanMethod
from tgapp.domain.kinetics.diagnostics import (
    RunDiagnostic,
    AlphaDiagnostic,
    StudyDiagnosticReport,
    diagnose_study,
    diagnose_analysis_result,
)
from tgapp.domain.kinetics.models import (
    KineticRun,
    KineticStudy,
    ConversionSettings,
    HeatingProgram,
    HeatingValidationSettings,
    IsoconversionalRun,
    IsoconversionalPoint,
    IsoconversionalDataset,
    LinearRegressionResult,
    KineticPointResult,
    KineticAnalysisResult,
    KineticQualitySettings,
)
from tgapp.domain.kinetics.units import (
    TemperatureUnit,
    TimeUnit,
    MassUnit,
    to_kelvin,
    to_seconds,
    to_grams,
)

__all__ = [
    # constants
    "GAS_CONSTANT_J_MOL_K",
    "OFW_DOYLE_SLOPE_FACTOR",
    # errors
    "KineticError",
    "KineticValidationError",
    "InsufficientRunsError",
    "IdenticalHeatingRatesError",
    "ConversionCalculationError",
    "InterpolationError",
    "RegressionError",
    "PlateauNotFoundError",
    "HeatingProgramError",
    # methods
    "BaseKineticMethod",
    "OzawaFlynnWallMethod",
    "KissingerAkahiraSunoseMethod",
    "FriedmanMethod",
    # diagnostics
    "RunDiagnostic",
    "AlphaDiagnostic",
    "StudyDiagnosticReport",
    "diagnose_study",
    "diagnose_analysis_result",
    # models
    "KineticRun",
    "KineticStudy",
    "ConversionSettings",
    "HeatingProgram",
    "HeatingValidationSettings",
    "IsoconversionalRun",
    "IsoconversionalPoint",
    "IsoconversionalDataset",
    "LinearRegressionResult",
    "KineticPointResult",
    "KineticAnalysisResult",
    "KineticQualitySettings",
    # units
    "TemperatureUnit",
    "TimeUnit",
    "MassUnit",
    "to_kelvin",
    "to_seconds",
    "to_grams",
]