from __future__ import annotations

from dash import Dash, Input, Output  # pyright: ignore[reportMissingImports]

from tgapp.application.use_cases import process_session
from tgapp.domain.models import ProcessingSettings
from tgapp.infrastructure.storage import SessionStorage


def _storage_from_app(app: Dash) -> SessionStorage:
    return SessionStorage(app.server.config["TGAPP_SESSION_DIR"])


def _is_checked(values: list[str] | None) -> bool:
    return bool(values and "on" in values)


def register_processing_callbacks(app: Dash) -> None:
    storage = _storage_from_app(app)

    @app.callback(
        Output("processing-store", "data"),
        Input("session-store", "data"),
        Input("init-mass", "value"),
        Input("bins", "value"),
        Input("mass-smoothing", "value"),
        Input("temp-smoothing", "value"),
        Input("difflag", "value"),
        Input("span", "value"),
        Input("use-correction", "value"),
        Input("smooth-dmdt", "value"),
        Input("hide-tg", "value"),
        Input("hide-dta", "value"),
        Input("hide-dtg", "value"),
        Input("hide-peaks-dta", "value"),
        Input("hide-peaks-dmdt", "value"),
    )
    def sync_processing_state(
        session_data: dict[str, object],
        init_mass: float | None,
        bins: int | None,
        mass_smoothing: int | None,
        temp_smoothing: int | None,
        difflag: int | None,
        span: float | None,
        use_correction: list[str] | None,
        smooth_dmdt: list[str] | None,
        hide_tg: list[str] | None,
        hide_dta: list[str] | None,
        hide_dtg: list[str] | None,
        hide_peaks_dta: list[str] | None,
        hide_peaks_dmdt: list[str] | None,
    ) -> dict[str, object]:
        settings = ProcessingSettings(
            init_mass=float(init_mass or 1.0),
            bins=int(bins or 1000),
            mass_smoothing=int(mass_smoothing or 1),
            temp_smoothing=int(temp_smoothing or 1),
            difflag=int(difflag or 1),
            use_correction=_is_checked(use_correction),
            smooth_dmdt=_is_checked(smooth_dmdt),
            span=float(span or 91),
            hide_tg=_is_checked(hide_tg),
            hide_dta=_is_checked(hide_dta),
            hide_dtg=_is_checked(hide_dtg),
            hide_peaks_dta=_is_checked(hide_peaks_dta),
            hide_peaks_dmdt=_is_checked(hide_peaks_dmdt),
        )
        return process_session(storage, session_data, settings)
