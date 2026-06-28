# AGENTS.md

## Scope
- Repo is Python migration of original R Shiny app. Original source at `../tg.app`.
- For behavior/parity questions, check `../tg.app/app.r`, `../tg.app/ui/ui.r`, and especially `../tg.app/server/server.r`.

## App wiring
- Real app is FastAPI. CLI: `tgapp = "tgapp.main:main"` in `pyproject.toml`.
- Startup: `src/tgapp/main.py` → `tgapp.web.app:create_app()` → routers in `src/tgapp/web/routes/`.
- `src/tgapp/web/app_factory.py` is stale Dash-era code; ignore unless reviving Dash.

## Current state
- First-tab workflow usable end-to-end: upload → process → plot → brush effect → export/import session.
- File parser fixed: space-separated headerless files now parse correctly (`_read_frame` + `_normalize_columns`).
- Plot rendering fixed: `/process` sends Plotly `{data, layout}` with safe JSON arrays.
- Upload compatibility lenient: accepts legacy R field names (`thermogramm`, `data`) and current names (`thermograms`, `session_file`).
- **Noise fix** (mass-noise-fix deepwork): pre-smoothing rounding removed, SG smoothing enabled by default (window=11), adaptive 5σ prominence filter on peaks, TGA2 DTG SG smoothing with UI slider.
- **UI redesign**: modern CSS with design tokens (system fonts, pill tabs, flat buttons, custom sliders), Plotly visual alignment (system fonts, grid colors, legend styling).
- Remaining gaps:
  - `/export/plot` returns `501 Not Implemented`
  - smoothing approximates R `sm.spline(...)`, not exact
  - peak detection approximates `stat_peaks/stat_valleys`, not exact
  - summary tab adapted for processed-data/debug, not literal R output
  - app depends on external CDNs for htmx and Plotly

## Verified commands
- Run: `uv run tgapp` or `uv run python -m tgapp.main`
- With base path: `APP_BASE_PATH=/tg uv run tgapp`
- Smoke: `uv run python -m compileall src`
- Server restart: `pkill -9 -f "python -m tgapp.main" 2>/dev/null; sleep 1; uv run python -m tgapp.main > /tmp/opencode/tgapp.log 2>&1 &`
- Verify alive: `ss -ltnp | grep ':8050' || true`

## Real-file smoke
- Sample: `samples/Сосна/Сосна 600_10_250мг.dat` → 1000 rows, heat speed ~9.8 K/мин.
- Workflow: upload `.dat` → `Обработать` → plot renders → brush effect → export `.tg`.

## Gotchas
- `APP_BASE_PATH` normalized in `src/tgapp/config.py`; never hardcode root-relative URLs bypassing it.
- Session cookie: `tgapp_session_id` in `src/tgapp/web/deps.py`. Server-side files under `.session-data/`.
- `README.md` / `pyproject.toml` contain stale migration text. Trust `src/tgapp/` layout.
- `mixchar` tab out of scope. Do not use as migration proof.
- Templates load htmx and Plotly from CDNs. App not local-only yet.

## High-value files
- Processing: `src/tgapp/application/use_cases.py`, `src/tgapp/domain/processing.py`, `src/tgapp/domain/peaks.py`, `src/tgapp/domain/summary.py`
- Smoothing/binning: `src/tgapp/domain/smoothing.py`, `src/tgapp/domain/thermogram.py`
- Plumbing: `src/tgapp/web/deps.py`, `src/tgapp/infrastructure/storage.py`, `src/tgapp/infrastructure/file_parsers.py`
- Routes: `src/tgapp/web/routes/pages.py`, `src/tgapp/web/routes/processing.py`, `src/tgapp/web/routes/uploads.py`
- Plotting: `src/tgapp/infrastructure/plotting.py`, `src/tgapp/infrastructure/serialization.py`
- Frontend: `src/tgapp/web/static/app.js`, `src/tgapp/web/templates/partials/thermogram_tab.html`

## Testing
- No repo-local test/lint/typecheck config. Do not invent nonexistent commands.
- Prefer targeted smoke: compileall + import check + route-specific manual check.

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
- Wait 1s
- Verify zero console errors
- Re-check "ДТА", click "Обновить" — plot restores

### 6. Verify SG controls
- In TGA1 tab, check "Savitzky-Golay сглаживание"
- Verify SG sliders ("Сглаживание массы", "Сглаживание температуры") become visible
- Click "Обработать" — plot re-renders with smoothed data
- Uncheck SG — sliders hide — plot re-renders without smoothing

### 7. Final check
- `browser_console_messages` level=error → must return 0 errors
- If any step fails, capture screenshot: `browser_take_screenshot` type=png
