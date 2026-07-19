from .create_session import create_session
from .upload_thermograms import upload_thermograms, upload_correction
from .process_thermograms import process_thermograms
from .calculate_effect import calculate_effect
from .import_session import import_session
from .export_session import export_session
from .get_plot_payload import get_plot_payload
from .get_raw_plot import get_raw_plot

# Backward-compatible aliases for existing test imports
process_session = process_thermograms  # renamed
load_thermograms = upload_thermograms  # renamed
load_correction = upload_correction  # renamed
import_saved_session = import_session  # renamed
export_session_archive = export_session  # renamed
get_effect_text = calculate_effect  # renamed
get_visible_thermogram_plot_json = None  # infra-dependent, stays in routes
get_heat_speed_text = None  # moved to view_models
get_summary = None  # moved to view_models
get_raw_plot_frame = get_raw_plot  # renamed

__all__ = [
    "create_session",
    "upload_thermograms",
    "upload_correction",
    "process_thermograms",
    "process_session",  # backward compat
    "calculate_effect",
    "get_effect_text",  # backward compat
    "import_session",
    "import_saved_session",  # backward compat
    "export_session",
    "export_session_archive",  # backward compat
    "get_plot_payload",
    "get_visible_thermogram_plot_json",  # backward compat (None - infra-dependent)
    "get_heat_speed_text",  # backward compat (None - moved)
    "get_summary",  # backward compat (None - moved)
    "get_raw_plot",
    "get_raw_plot_frame",  # backward compat
    "load_thermograms",  # backward compat
    "load_correction",  # backward compat
]