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
