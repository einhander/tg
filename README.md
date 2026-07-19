# tg-py — термограмма обробка

FastAPI web application for TGA/DTG thermogram processing. Migration of the original R Shiny app (`../tg.app`).

## Stack

FastAPI + Jinja2 + HTMX + Plotly

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

## Configuration

Environment variables:

- `APP_HOST` (default: `127.0.0.1`)
- `APP_PORT` (default: `8050`)
- `APP_DEBUG` (default: `false`)
- `APP_BASE_PATH` (default: `/`)
- `APP_SESSION_DIR` (default: `.session-data`)

`APP_BASE_PATH` is normalized so the FastAPI app can be served from a subdirectory such as `/tg`.

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