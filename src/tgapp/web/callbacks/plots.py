from __future__ import annotations

from dash import Dash, Input, Output  # pyright: ignore[reportMissingImports]

from tgapp.application.use_cases import get_effect_text, get_heat_speed_text, get_plot_payload, get_summary
from tgapp.domain.models import ProcessingSettings
from tgapp.infrastructure.plotting import build_deconv_placeholder, build_main_plot, build_mixchar_placeholder
from tgapp.infrastructure.serialization import to_json
from tgapp.infrastructure.storage import SessionStorage


def _storage_from_app(app: Dash) -> SessionStorage:
    return SessionStorage(app.server.config["TGAPP_SESSION_DIR"])


def register_plot_callbacks(app: Dash) -> None:
    storage = _storage_from_app(app)

    @app.callback(
        Output("main-plot", "figure"),
        Output("mixchar-plot", "figure"),
        Output("deconv-plot", "figure"),
        Output("summary-output", "children"),
        Output("heat-speed-output", "children"),
        Output("effect-output", "children"),
        Input("session-store", "data"),
        Input("processing-store", "data"),
        Input("main-plot", "selectedData"),
    )
    def update_plots(session_data: dict[str, object], processing_data: dict[str, object], selected_data: dict[str, object] | None):
        settings = processing_data.get("settings", {}) if isinstance(processing_data, dict) else {}
        processing_settings = ProcessingSettings(**settings if isinstance(settings, dict) else {})
        payload = get_plot_payload(storage, session_data, processing_settings)
        summary = get_summary(processing_data)
        xmin: float | None = None
        xmax: float | None = None
        if isinstance(selected_data, dict):
            points = selected_data.get("points")
            if isinstance(points, list):
                x_values = [float(point["x"]) for point in points if isinstance(point, dict) and "x" in point]
                if x_values:
                    xmin = min(x_values)
                    xmax = max(x_values)
        return (
            build_main_plot(payload),
            build_mixchar_placeholder(),
            build_deconv_placeholder(),
            to_json({"lines": summary.lines, "metrics": summary.metrics}),
            get_heat_speed_text(processing_data),
            get_effect_text(storage, session_data, processing_settings, xmin, xmax),
        )
