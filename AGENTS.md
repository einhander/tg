# tg-py — Agents

## What this is

Thermogram pre-processing web app. Python migration of the original R Shiny app (`../tg.app`).
Uploads TGA/DTG data files, processes them, and visualizes results with Plotly.

For behavior/parity questions, check `../tg.app/app.r`, `../tg.app/ui/ui.r`, and especially `../tg.app/server/server.r`.

## Quick start

```bash
# Run dev server (port 8050) — uv handles venv activation
uv run tgapp
# or: uv run python -m tgapp.main

# Dev mode (uvicorn reload on save)
APP_DEBUG=1 uv run tgapp

# With base path (reverse-proxy deploys)
APP_BASE_PATH=/tg uv run tgapp
```

## Smoke testing

```bash
# Syntax check all Python files
uv run python -m compileall src

# Restart server cleanly
pkill -9 -f "python -m tgapp.main"; sleep 1
uv run python -m tgapp.main > /tmp/tgapp.log 2>&1 &

# Verify server is listening
ss -ltnp | grep ':8050' || true
```

## Real-file smoke test

Sample: `samples/Береза/Береза600_10_3140.dat` → 1000 rows, heat speed ~9.8 K/min.
Expected workflow: upload `.dat` → click "Обработать" → plot renders → click checkbox.

## Architecture

Clean-architecture layers inside `src/tgapp/`:

| Layer | Path | Responsibility |
|---|---|---|
| **Web** | `web/` | FastAPI app (`app.py`), routes (`routes/`), session deps (`deps.py`), Jinja2 templates (`templates/`), static files (`static/`) |
| **Application** | `application/` | Use cases (`use_cases/`), DTOs (`dto.py`), ports (`ports.py`), session state (`session_state.py`), view models (`view_models.py`), error responses (`error_responses.py`) |
| **Domain** | `domain/` | Models (`models.py`), processing engine (`processing_engine.py`), peak detection (`peaks.py`), smoothing (`smoothing.py`), summaries (`summary.py`), thermogram normalization (`thermogram.py`), alignment (`alignment.py`), correction (`correction.py`), effects (`effects.py`), validation (`validator.py`) |
| **Infrastructure** | `infrastructure/` | File I/O (`storage.py`), file parsing (`file_parsers.py`), plotting helpers (`plotting.py`), session archive serialization (`serialization.py`) — also handles numpy → JSON sanitization |

**Entry point:** `src/tgapp/main.py` → `AppConfig.from_env()` → `create_app(config)` → `uvicorn.run()`

## Processing Engine

`domain/processing_engine.py` — unified processing pipeline (PLAN_PRE_OZF):

```
parse → validate → normalize units → determine common physical range
→ align each experiment → smooth each experiment → calculate derivatives (np.gradient, edge_order=2)
→ apply correction (strict, no silent skip) → aggregate traces → detect peaks → calculate summary
→ return immutable ProcessingResult
```

Key steps:
1. **Re-validation** — defensive check on already-validated thermograms
2. **Alignment** — interpolate all experiments onto common temperature grid
3. **Correction** — apply temperature correction curve (if enabled); raises `CorrectionRangeError` if missing/misaligned
4. **Per-experiment smoothing** — Savitzky-Golay or moving average per trace
5. **Per-run DTG** — `np.gradient(mass, time, edge_order=2)` per experiment, then average
6. **Aggregation** — mean of mass, temp, time, deltatemp traces
7. **Post-aggregation smoothing** — derivative (DTG) smoothing on mean; temperature is NEVER smoothed (physical axis)
8. **Peak detection** — scipy `find_peaks` with prominence filtering
9. **Rounding** — output precision matching legacy pipeline

## Config (env vars)

| Variable | Default | Note |
|---|---|---|
| `APP_HOST` | `127.0.0.1` | Bind address |
| `APP_PORT` | `8050` | Port |
| `APP_DEBUG` | `false` | Enable uvicorn reload |
| `APP_BASE_PATH` | `/` | URL prefix for reverse-proxy deploys |
| `APP_SESSION_DIR` | `.session-data` | Where session files live |
| `APP_MAX_UPLOAD_SIZE` | `52428800` | 50 MB per upload |
| `APP_MAX_UPLOAD_FILES` | `10` | Max files per upload |
| `APP_MAX_ARCHIVE_SIZE` | `104857600` | 100 MB max archive |
| `APP_MAX_DATA_ROWS` | `1000000` | Max data rows per file |
| `APP_SESSION_TTL` | `86400` | 24 hours session TTL |
| `APP_MAX_SESSION_SIZE` | `524288000` | 500 MB max session |

## Session storage

All session data is file-based in `.session-data/{session_id}/`:
- `thermograms/*.csv` — parsed thermogram frames
- `raw_thermograms/*.csv` — raw copies
- `validated_thermograms/*.csv` — validated thermogram frames
- `correction.csv` — temperature correction file
- `processed.csv` — processed output
- `settings.json` — last processing settings
- `tga2-settings.json` — TGA2 plot settings
- `thermogram_settings.json` — unified thermogram view settings
- `metadata.json` — status, original names, last process summary

Session ID is stored in an httponly cookie (`tgapp_session_id`). No server-side session store.

## Routes

All under `web/routes/`, aggregated in `routes/__init__.py`:
- `pages.py` — HTML page rendering (Jinja2 templates in `web/templates/`)
- `uploads.py` — file upload handlers (thermograms, correction, session archive import)
- `processing.py` — run processing, get plot data, settings
- `effects.py` — thermal effect calculation on temperature range selection
- `exports.py` — download plot as PNG, export session as `.tg` archive (ZIP format)

## Templates

Jinja2 templates in `web/templates/`. Static files in `web/static/` (mounted at `/static`).

Tab structure (`index.html`):
- **Термограмма** — `partials/tga2_tab.html` (settings form + plot + visibility toggles + SG controls)
- **Деконволюция** — `partials/mixchar_tab.html` (placeholder)
- **Debug** — `partials/summary_tab.html` (processed data / debug output)

## Domain models

- `ThermogramFile` — uploaded thermogram data (name, DataFrame, metadata)
- `CorrectionFile` — temperature correction curve
- `ProcessingSettings` — all processing parameters (mass, smoothing, bins, difflag, span, etc.)
- `ThermogramViewSettings` — plot visibility controls (hide TG/DTG/peaks, SG parameters)
- `ThermogramProcessed` — combined/smoothed/derivative frames, peaks, summary
- `PeakResult` — detected peak (x, y, label, kind, extremum)
- `SummaryResult` — summary lines and metrics
- `ParsedThermogram` — raw parsed data (temp, deltatemp, time, mass as numpy arrays)
- `ValidatedThermogram` — validated data (monotonicity checks, row counts)
- `AlignedThermogram` — interpolated on common temperature grid
- `ProcessingResult` — immutable result of the full processing pipeline

## Application layer

- **Use cases** (`use_cases/`) — `create_session`, `upload_thermograms`, `process_thermograms`, `get_plot_payload`, `get_raw_plot`, `calculate_effect`, `export_session`, `import_session`
- **Ports** (`ports.py`) — `SessionRepository`, `ThermogramParser`, `SessionArchiveService`, `ProcessingResultRepository` (Protocol-based dependency inversion)
- **DTOs** (`dto.py`) — `UploadPayload`, `UiMessage`, `PlotPayload`, `SessionStateDto`, `ProcessingStateDto`
- **Error responses** (`error_responses.py`) — user-facing messages, severity levels, factory functions mapping domain exceptions to `UserError`

## File formats

File parsers (`infrastructure/file_parsers.py`) auto-detect CSV separators (`,`, `;`, `\t`, whitespace).
Column name normalization maps common variants → `temp`, `deltatemp`, `time`, `mass`.
Headerless files are mapped by column index (0=temp, 1=deltatemp, 2=time, 3=mass).

Sample data lives in `samples/` (various TGA formats).

## Dependencies

Managed by **uv** (`uv.lock`). Python ≥3.10.

**Runtime:** fastapi, jinja2, plotly, pandas, python-multipart, scipy, numpy, uvicorn

**Dev:** pytest, pytest-cov, httpx, ruff

## Security

- Session IDs validated against UUID format before filesystem access
- Upload size limits enforced (configurable via env vars)
- Archive unpacking size limits enforced (PLAN_AUDIT §16.4)
- ZIP entries validated against path traversal
- Cookie uses `httponly=True`, `samesite="lax"`, `secure` flag in production
- No server-side session store — file-based with TTL

## Scientific improvements

- **Per-run DTG:** dm/dt calculated per experiment via `np.gradient(..., edge_order=2)`, then averaged — not on aggregated data
- **Linear regression heating rate:** slope of temp vs time in °C/min (not average ΔT/Δt)
- **Baseline integration:** trapezoidal integration with baseline correction for peak area
- **scipy find_peaks:** proper peak detection with prominence filtering (not simple diff-based)
- **Savitzky-Golay smoothing:** `scipy.signal.savgol_filter` for mass, temperature, and derivative columns
- **Temperature never smoothed:** temp is a physical axis
- **Correction strict:** raises `CorrectionRangeError` if correction requested but missing/misaligned
- **Streaming uploads:** 8KB chunks, no Base64 encoding, size limit enforcement

## Domain exceptions

- `ThermogramValidationError` — base class for validation errors
- `DerivativeCalculationError` — invalid derivative computation (NaN/inf, non-monotonic time, insufficient data)
- `CorrectionRangeError` — correction file doesn't cover working range or missing
- `NonMonotonicAxisError` — axis not strictly increasing
- `InsufficientDataError` — too few data points

## Error handling

User-facing error messages via `application/error_responses.py` — all in Russian, never expose internal paths or tracebacks. Error severity levels: info, warning, error. Domain exceptions (`ThermogramValidationError` hierarchy) map to user-friendly messages.

## Package layout

`src/` layout via setuptools. Import path is `tgapp.*`.

## Testing

No repo-local test/lint/typecheck config. Do not invent nonexistent commands.
Prefer targeted smoke: compileall + import check + route-specific manual check.

## Gotchas

- `APP_BASE_PATH` normalized in `config.py`; never hardcode root-relative URLs bypassing it.
- Mixchar/Деконволюция tab is placeholder. Do not use as migration proof.
- Templates load htmx and Plotly from CDNs. App not local-only yet.
- `/export/plot` returns `501 Not Implemented` — plot export not yet built.
- Smoothing approximates R `sm.spline(...)`, not exact. Peak detection approximates `stat_peaks/stat_valleys`, not exact.

## High-value files

- Processing: `domain/processing_engine.py`, `domain/peaks.py`, `domain/summary.py`
- Smoothing/binning: `domain/smoothing.py`, `domain/thermogram.py`, `domain/alignment.py`
- Application: `application/use_cases/`, `application/ports.py`, `application/error_responses.py`
- Plumbing: `web/deps.py`, `infrastructure/storage.py`, `infrastructure/file_parsers.py`
- Routes: `web/routes/pages.py`, `web/routes/processing.py`, `web/routes/uploads.py`
- Plotting: `infrastructure/plotting.py`, `infrastructure/serialization.py`
- Frontend: `web/static/app.js`, `web/templates/partials/tga2_tab.html`

## Playwright verification sequence

Run after any plot/settings/visibility change. Server must be running on `:8050`.

### 1. Navigate
```
browser_navigate → http://127.0.0.1:8050/
```

### 2. Upload sample thermogram
- Click "Файл термограммы" button
- `browser_file_upload` → `samples/Сосна/Сосна 600_10_250мг.dat`
- Click "Загрузить" button
- Wait 2s, verify "Loaded 1 thermogram file(s)" appears

### 3. Verify Thermogram tab — process and plot
- Click "Термограмма" tab link
- Snapshot tabpanel, verify settings form visible (SG checkbox, peak threshold, etc.)
- Click "Обработать" button
- Wait 2s
- Snapshot tabpanel, verify:
  - Heat speed shows "Скорость нагрева: 9.8 K/мин"
  - Plot renders (contains SVG or Plotly logo link)
  - Effect text visible
- `browser_console_messages` level=error → must return 0 errors

### 4. Verify visibility toggles
- In Thermogram tab, uncheck "ДТА", click "Обновить"
- Wait 1s, verify zero console errors
- Re-check "ДТА", click "Обновить" — plot restores

### 5. Verify SG controls
- In Thermogram tab, check "Savitzky-Golay сглаживание"
- Verify SG sliders become visible
- Click "Обработать" — plot re-renders with smoothed data
- Uncheck SG — sliders hide — plot re-renders without smoothing

### 6. Final check
- `browser_console_messages` level=error → must return 0 errors
- If any step fails, capture screenshot: `browser_take_screenshot` type=png