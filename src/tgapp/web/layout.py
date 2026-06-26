from __future__ import annotations

from dash import dcc, html  # pyright: ignore[reportMissingImports]

from tgapp.application.dto import PlotPayload
from tgapp.application.session_state import create_default_processing_state, create_default_session_state
from tgapp.infrastructure.plotting import build_deconv_placeholder, build_main_plot, build_mixchar_placeholder


def _checkbox(label: str, component_id: str, value: bool = False) -> html.Label:
    return html.Label([dcc.Checklist(id=component_id, options=[{"label": label, "value": "on"}], value=["on"] if value else [])])


def _sidebar_control(label: str, component: object) -> html.Div:
    return html.Div(className="sidebar-control", children=[html.Label(label, className="sidebar-label"), component])


def create_layout() -> html.Div:
    return html.Div(
        className="app-shell",
        children=[
            dcc.Location(id="url"),
            dcc.Store(id="session-store", data=create_default_session_state()),
            dcc.Store(id="processing-store", data=create_default_processing_state()),
            dcc.Download(id="download-plot"),
            dcc.Download(id="download-session"),
            html.Header(
                className="page-header",
                children=[
                    html.H1("Предобработка дериватограммы", className="page-title"),
                ],
            ),
            html.Main(
                className="page-content",
                children=[
                    html.Aside(
                        className="sidebar panel",
                        children=[
                            _sidebar_control(
                                "Файл термограммы",
                                dcc.Upload(id="upload-thermograms", className="upload-box", children=html.Div(["Выберите файлы термограммы"]), multiple=True),
                            ),
                            _sidebar_control(
                                "Файл tg",
                                dcc.Upload(id="upload-session-tg", className="upload-box", children=html.Div(["Выберите файл tg"]), multiple=False),
                            ),
                            _sidebar_control("Начальная масса", dcc.Input(id="init-mass", type="number", value=1.0, className="text-input")),
                            _sidebar_control("Скорость нагрева", html.Div(id="heat-speed-output", className="status-box", children="Данные еще не загружены")),
                            _sidebar_control(
                                "Файл коррекции температуры",
                                dcc.Upload(id="upload-correction", className="upload-box", children=html.Div(["Выберите файл коррекции"]), multiple=False),
                            ),
                            html.Div(className="sidebar-control checkbox-control", children=[_checkbox("Использовать коррекцию", "use-correction")]),
                            _sidebar_control("Bins", dcc.Slider(id="bins", min=1, max=2000, step=1, value=1000, tooltip={"placement": "bottom", "always_visible": False})),
                            _sidebar_control("Сглаживание массы", dcc.Slider(id="mass-smoothing", min=1, max=500, step=1, value=1, tooltip={"placement": "bottom", "always_visible": False})),
                            _sidebar_control("Сглаживание температуры", dcc.Slider(id="temp-smoothing", min=1, max=100, step=1, value=1, tooltip={"placement": "bottom", "always_visible": False})),
                            _sidebar_control("Difflag", dcc.Slider(id="difflag", min=1, max=100, step=1, value=1, tooltip={"placement": "bottom", "always_visible": False})),
                            html.Div(className="sidebar-control checkbox-control", children=[_checkbox("Сглаживать dmdt", "smooth-dmdt", value=False)]),
                            _sidebar_control("Span", dcc.Slider(id="span", min=1, max=100, step=1, value=91, tooltip={"placement": "bottom", "always_visible": False})),
                            html.Div(id="upload-status", className="status-box"),
                        ],
                    ),
                    html.Section(
                        className="main-panel panel",
                        children=[
                            dcc.Tabs(
                                className="main-tabs",
                                parent_className="main-tabs-wrap",
                                children=[
                                    dcc.Tab(
                                        label="Термограмма",
                                        className="main-tab",
                                        selected_className="main-tab main-tab-selected",
                                        children=[
                                            html.Div(
                                                className="tab-pane-body",
                                                children=[
                                                    html.Div(
                                                        className="hide-controls-row",
                                                        children=[
                                                            _checkbox("ТГ", "hide-tg"),
                                                            _checkbox("ДТА", "hide-dta"),
                                                            _checkbox("ТГП", "hide-dtg"),
                                                            _checkbox("Пики ДТА", "hide-peaks-dta"),
                                                            _checkbox("Пики dmdt", "hide-peaks-dmdt"),
                                                        ],
                                                    ),
                                                    html.Div(
                                                        className="plot-panel",
                                                        children=[
                                                            dcc.Graph(id="main-plot", figure=build_main_plot(PlotPayload()), config={"modeBarButtonsToAdd": ["select2d", "lasso2d"]}, className="main-graph"),
                                                        ],
                                                    ),
                                                    html.Div(className="button-row", children=[html.Button("Скачать график", id="download-plot-button", n_clicks=0, className="app-button"), html.Button("Скачать CSV", id="download-session-button", n_clicks=0, className="app-button")]),
                                                    html.Pre(id="effect-output", className="effect-output", children="Эффект: выберите температурный интервал"),
                                                ],
                                            ),
                                        ],
                                    ),
                                    dcc.Tab(
                                        label="Графики Mixchar",
                                        className="main-tab",
                                        selected_className="main-tab main-tab-selected",
                                        children=[
                                            html.Div(
                                                className="tab-pane-body",
                                                children=[
                                                    html.Div(className="plot-panel", children=[dcc.Graph(id="mixchar-plot", figure=build_mixchar_placeholder())]),
                                                    html.Div(className="results-placeholder", children=[html.H4("Результаты"), html.P("Расчетная область и разложение будут показаны здесь.")]),
                                                    html.Div(className="plot-panel", children=[dcc.Graph(id="deconv-plot", figure=build_deconv_placeholder())]),
                                                ],
                                            ),
                                        ],
                                    ),
                                    dcc.Tab(
                                        label="Summary",
                                        className="main-tab",
                                        selected_className="main-tab main-tab-selected",
                                        children=[html.Div(className="tab-pane-body", children=[html.Pre(id="summary-output", children="Ожидание загрузки данных...", className="summary-output")])],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        ],
    )
