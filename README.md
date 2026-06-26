# tg.app Python migration skeleton

This directory contains a minimal Python FastAPI skeleton for migrating the existing R Shiny app.

## Status

- R app remains unchanged.
- Python app is a runnable placeholder with layered structure.
- UI, callbacks, storage, and domain/application modules are scaffolding for future migration work.

## Run

```bash
cd python-app
python -m venv .venv
source .venv/bin/activate
pip install -e .
tgapp
```

Or:

```bash
cd python-app
PYTHONPATH=src python -m tgapp.main
```

## Configuration

Environment variables:

- `APP_HOST` (default: `127.0.0.1`)
- `APP_PORT` (default: `8050`)
- `APP_DEBUG` (default: `false`)
- `APP_BASE_PATH` (default: `/`)
- `APP_SESSION_DIR` (default: `./.session-data`)

`APP_BASE_PATH` is normalized so the FastAPI app can be served from a subdirectory such as `/tg`.

## Notes

- Layout includes placeholder upload controls, graphs, stores, and download components.
- Callback modules are registered and safe to import, but currently provide placeholder behavior only.
- File parsing, processing, plotting, and serialization modules define migration-oriented interfaces without full business logic yet.
