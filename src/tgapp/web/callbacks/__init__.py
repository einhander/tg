from __future__ import annotations

from dash import Dash  # pyright: ignore[reportMissingImports]

from tgapp.web.callbacks.exports import register_export_callbacks
from tgapp.web.callbacks.plots import register_plot_callbacks
from tgapp.web.callbacks.processing import register_processing_callbacks
from tgapp.web.callbacks.uploads import register_upload_callbacks


def register_callbacks(app: Dash) -> None:
    register_upload_callbacks(app)
    register_processing_callbacks(app)
    register_plot_callbacks(app)
    register_export_callbacks(app)
