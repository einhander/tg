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

# With base path (reverse-proxy deploys)
APP_BASE_PATH=/tg uv run tgapp

# Dev mode (uvicorn reload on save)
APP_DEBUG=1 uv run tgapp
```

## Smoke testing

```bash
# Syntax check all Python files
uv run python -m compileall src

# Restart server cleanly
pkill -9 -f "python -m tgapp.main" 2>/dev/null; sleep 1
uv run python -m tgapp.main > /tmp/tgapp.log 2>&1 &

# Verify server is listening
ss -ltnp | grep ':8050' || true
```

## Real-file smoke test

Sample: `samples/Сосна/Сосна 600_10_250мг.dat` → 1000 rows, heat speed ~9.8 K/min.
Expected workflow: upload `.dat` → click "Обработать" → plot renders → brush effect → export `.tg`.

## Architecture

Clean-architecture layers inside `src/tgapp/`:

| Layer | Path | Responsibility |
|---|---|---|
| **Web** | `web/` | FastAPI app (`app.py`), routes (`routes/`), session deps (`deps.py`), Dash layout (`layout.py`), Dash callbacks (`callbacks/`), Dash factory (`app_factory.py`) |
| **Application** | `application/` | Use cases (`use_cases.py`), DTOs (`dto.py`), session state factories (`session_state.py`), view models (`view_models.py`) |
| **Domain** | `domain/` | Models (`models.py`), processing logic (`processing.py`), peak detection (`peaks.py`), smoothing (`smoothing.py`), summaries (`summary.py`), thermogram normalization (`thermogram.py`) |
| **Infrastructure** | `infrastructure/` | File I/O (`storage.py`), file parsing (`file_parsers.py`), plotting helpers (`plotting.py`), session archive serialization (`serialization.py`) — note: `serialization.py` also handles numpy → JSON sanitization

**Entry point:** `src/tgapp/main.py` → `AppConfig.from_env()` → `create_app(config)` → `uvicorn.run()`

## Config (env vars)

| Variable | Default | Note |
|---|---|---|
| `APP_HOST` | `127.0.0.1` | Bind address |
| `APP_PORT` | `8050` | Port |
| `APP_DEBUG` | `false` | Enable uvicorn reload |
| `APP_BASE_PATH` | `/` | URL prefix for reverse-proxy deploys |
| `APP_SESSION_DIR` | `.session-data` | Where session files live |

## Session storage

All session data is file-based in `.session-data/{session_id}/`:
- `thermograms/*.csv` — parsed thermogram frames
- `raw_thermograms/*.csv` — raw copies
- `correction.csv` — temperature correction file
- `processed.csv` — processed output
- `settings.json` — last processing settings
- `tga2-settings.json` — TGA2 plot settings
- `metadata.json` — status, original names, last process summary

Session ID is stored in an httponly cookie (`tgapp_session_id`). No server-side session store.

## Routes

All under `web/routes/`, aggregated in `routes/__init__.py`:
- `pages.py` — HTML page rendering (Jinja2 templates in `web/templates/`)
- `uploads.py` — file upload handlers (thermograms, correction, session archive import)
- `processing.py` — run processing, get plot data, settings
- `effects.py` — thermal effect calculation on temperature range selection
- `exports.py` — download plot as PNG, export session as `.tg` archive (ZIP format)

## Active stack: FastAPI only

`main.py` imports `create_app` from `web/app.py` (FastAPI). The Dash factory in `web/app_factory.py` is **dead code** — not imported anywhere in the codebase. Safe to remove.

Dash components (`layout.py`, `callbacks/`) are used only for building the initial HTML layout rendered server-side via Jinja2 templates. No client-side Dash callbacks are wired.

Templates live in `web/templates/` (Jinja2). Static files in `web/static/` (mounted at `/static`).

## Domain models

- `ThermogramFile` — uploaded thermogram data (name, DataFrame, metadata)
- `CorrectionFile` — temperature correction curve
- `ProcessingSettings` — all processing parameters (mass, smoothing, bins, difflag, span, etc.)
- `ThermogramProcessed` — combined/smoothed/derivative frames, peaks, summary
- `PeakResult` — detected peak (x, y, label, kind)

## File formats

File parsers (`infrastructure/file_parsers.py`) auto-detect CSV separators (`,`, `;`, `\t`, whitespace).
Column name normalization maps common variants → `temp`, `deltatemp`, `time`, `mass`.
Headerless files are mapped by column index (0=temp, 1=deltatemp, 2=time, 3=mass).

Sample data lives in `samples/` (various TGA formats).

## Dependencies

Managed by **uv** (`uv.lock`). Python ≥3.10.

Key deps: dash, fastapi, plotly, pandas, numpy, jinja2, uvicorn, python-multipart.

## Package layout

`src/` layout via setuptools. Import path is `tgapp.*`. No tests currently exist.

## Current state

- First-tab workflow usable end-to-end: upload → process → plot → brush effect → export/import session.
- File parser fixed: space-separated headerless files parse correctly.
- Plot rendering fixed: `/process` sends Plotly `{data, layout}` with safe JSON arrays.
- Upload compatibility lenient: accepts legacy R field names (`thermogramm`, `data`) and current names.
- **Noise fix**: SG smoothing enabled by default (window=11), adaptive 5σ prominence filter on peaks.
- **UI redesign**: modern CSS with design tokens, Plotly visual alignment.
- Remaining gaps:
  - `/export/plot` returns `501 Not Implemented`
  - smoothing approximates R `sm.spline(...)`, not exact
  - peak detection approximates `stat_peaks/stat_valleys`, not exact
  - summary tab adapted for processed-data/debug, not literal R output
  - app depends on external CDNs for htmx and Plotly

## Gotchas

- `APP_BASE_PATH` normalized in `config.py`; never hardcode root-relative URLs bypassing it.
- `README.md` / `pyproject.toml` contain stale migration text. Trust `src/tgapp/` layout.
- `mixchar` tab out of scope. Do not use as migration proof.
- Templates load htmx and Plotly from CDNs. App not local-only yet.

## High-value files

- Processing: `application/use_cases.py`, `domain/processing.py`, `domain/peaks.py`, `domain/summary.py`
- Smoothing/binning: `domain/smoothing.py`, `domain/thermogram.py`
- Plumbing: `web/deps.py`, `infrastructure/storage.py`, `infrastructure/file_parsers.py`
- Routes: `web/routes/pages.py`, `web/routes/processing.py`, `web/routes/uploads.py`
- Plotting: `infrastructure/plotting.py`, `infrastructure/serialization.py`
- Frontend: `web/static/app.js`, `web/templates/partials/thermogram_tab.html`

## Testing

No repo-local test/lint/typecheck config. Do not invent nonexistent commands.
Prefer targeted smoke: compileall + import check + route-specific manual check.

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

### 3. Verify TGA1 tab — process and plot
- Click "TGA1" tab link
- Snapshot tabpanel, verify settings form visible (bins, difflag, SG, etc.)
- Click "Обработать" button
- Wait 2s
- Snapshot tabpanel, verify:
  - Heat speed shows "Скорость нагрева: 9.8 K/мин"
  - Plot renders (contains SVG or Plotly logo link)
  - Effect text: "Тепловой эффект: выделите температурный интервал"
- `browser_console_messages` level=error → must return 0 errors

### 4. Verify TGA2 tab — raw plot stays independent
- Click "TGA2" tab link
- Snapshot tabpanel, verify:
  - "Настройки TGA2" heading visible
  - SG checkbox, TG/DTA checkboxes, "Обновить" button present
  - Plot renders (raw data, no processing artifacts)
- Uncheck "ТГ" in TGA2, click "Обновить"
- Wait 1s
- Switch back to TGA1 tab
- Verify TGA1 plot still shows TG (independence check)

### 5. Verify visibility toggles (TGA1)
- In TGA1 tab, uncheck "ДТА", click "Обновить"
- Wait 1s, verify zero console errors
- Re-check "ДТА", click "Обновить" — plot restores

### 6. Verify SG controls
- In TGA1 tab, check "Savitzky-Golay сглаживание"
- Verify SG sliders become visible
- Click "Обработать" — plot re-renders with smoothed data
- Uncheck SG — sliders hide — plot re-renders without smoothing

### 7. Final check
- `browser_console_messages` level=error → must return 0 errors
- If any step fails, capture screenshot: `browser_take_screenshot` type=png
