# AGENT_MEMORY.md

## Purpose
This file is a persistent memory/handoff for future agents after the project is moved to another folder or reopened in a fresh session.

Use it as the first orientation document before making further changes.

---

## Project identity
- Project name: `tg.app`
- Original app type: **R Shiny app**
- Current migration target: **Python web app**
- New UI stack chosen: **FastAPI + Jinja2 + htmx + Plotly**

The migration goal is **not** to redesign business logic from scratch.
The goal is to preserve the existing app behavior from the R Shiny version while replacing the UI/runtime layer with a Python implementation.

---

## Original repository structure and truth sources

Primary source files in the original app:
- `app.r`
- `ui/ui.r`
- `server/server.r`

Current location of original R app relative to this repo:
- `../tg.app`

Important facts:
- `app.r` is the real entrypoint.
- `app.r` sources:
  - `ui/ui.r`
  - `server/server.r`
- `ui/ui.r` is **not** a full page; it is a `tabPanel(...)` fragment inserted into a `navbarPage(...)` in `app.r`.
- Most app behavior and state handling live in `server/server.r`.
- The original app uses shared global reactive state via `values <- reactiveValues(...)`.

When in doubt about behavior, use `server/server.r` and `ui/ui.r` as the source of truth.

---

## Migration direction already decided

### Rejected direction
- Dash-based UI was explored and then rejected for visual/UX reasons.
- The user did not want the Dash look and wanted a more compact Shiny-like/internal-tool layout.

### Accepted direction
- Backend/web framework: `FastAPI`
- Templating: `Jinja2`
- Partial interaction updates: `htmx`
- Plot rendering: `Plotly`

Reasoning:
- Better control over layout and visual structure.
- Easier to shape into a compact internal tool.
- Better fit for server-rendered flows and lightweight interactions.

---

## User preferences already established

- Prefer **Python migration** over continuing with R UI.
- Prefer **FastAPI + Jinja2 + htmx + Plotly**.
- Prefer a **Shiny-like/internal-tool** appearance.
- Want the first/main screen to be **compact** and **one-screen oriented**.
- Want settings/controls **beside** the main graph, not stacked above it on desktop.
- Want **three top-level tabs**:
  1. `Настройки`
  2. `Деконволюция`
  3. `Debug`
- Want support for running behind a subpath/reverse proxy via `root_path` / base path.
- Prefer maximum delegation during implementation.
- User previously requested terse/caveman-style responses during active work, but this memory file should remain normal and explicit.

---

## Work completed so far

### 1) Repository understanding
- Inspected original R files:
  - `app.r`
  - `ui/ui.r`
  - `server/server.r`
- Added repo guidance in `AGENTS.md`.

### 2) Python app scaffold
- Created Python app in repository root package layout under:
  - `src/tgapp/`
- Established a layered structure:
  - `domain/`
  - `application/`
  - `infrastructure/`
  - `web/`

### 3) Logic porting from R to Python
Substantial processing behavior was ported into Python core layers, including:
- per-file resampling to `bins`
- adjusted `difflag`
- mean traces
- `dmdt`
- correction handling on `deltatemp`
- heat speed calculation
- effect calculation
- DTA/DTG peak overlays / extrema work

This means the Python app is not just a shell; meaningful domain logic already exists.

### 4) FastAPI routes and app plumbing
Implemented app/server routes for:
- `/`
- `/upload/thermograms`
- `/upload/correction`
- `/upload/session`
- `/process`
- `/effect`
- `/export/session`
- `/export/plot`

### 5) Templates and static assets
Created/maintained files for the FastAPI UI including:
- `base.html`
- `index.html`
- partial templates
- `styles.css`
- `app.js`

### 6) Runtime fixes already done
At least these two concrete issues were fixed:
- `TypeError: Jinja2Templates.TemplateResponse() missing 1 required positional argument: 'request'`
- `jinja2.exceptions.UndefinedError: 'session_state' is undefined`

The second fix involved making backend/template context more compatible with expected template keys.

### 7) Layout refactor already done
- UI was reshaped into a compact **3-tab** layout.
- CSS was revised so the settings pane stays left and the graph stays right for longer on desktop widths.

---

## Current Python structure worth checking first

### Top-level Python app files
- `pyproject.toml`
- `src/tgapp/main.py`
- `src/tgapp/config.py`

### Application layer
- `src/tgapp/application/use_cases.py`
- `src/tgapp/application/view_models.py`
- `src/tgapp/application/session_state.py`
- `src/tgapp/application/dto.py`

### Domain layer
- `src/tgapp/domain/processing.py`
- `src/tgapp/domain/summary.py`
- `src/tgapp/domain/peaks.py`
- `src/tgapp/domain/models.py`
- `src/tgapp/domain/smoothing.py`
- `src/tgapp/domain/thermogram.py`

### Infrastructure layer
- `src/tgapp/infrastructure/storage.py`
- `src/tgapp/infrastructure/file_parsers.py`
- `src/tgapp/infrastructure/plotting.py`
- `src/tgapp/infrastructure/serialization.py`

### Web layer
- `src/tgapp/web/app.py`
- `src/tgapp/web/app_factory.py`
- `src/tgapp/web/layout.py`
- `src/tgapp/web/deps.py`
- `src/tgapp/web/routes/pages.py`
- `src/tgapp/web/routes/uploads.py`
- `src/tgapp/web/routes/processing.py`
- `src/tgapp/web/routes/effects.py`
- `src/tgapp/web/routes/exports.py`
- `src/tgapp/web/callbacks/uploads.py`
- `src/tgapp/web/callbacks/processing.py`
- `src/tgapp/web/callbacks/plots.py`
- `src/tgapp/web/callbacks/exports.py`

### Templates / UI
- `src/tgapp/web/templates/index.html`
- `src/tgapp/web/templates/base.html`
- `src/tgapp/web/templates/partials/sidebar.html`
- `src/tgapp/web/templates/partials/thermogram_tab.html`
- `src/tgapp/web/templates/partials/summary_tab.html`
- `src/tgapp/web/templates/partials/mixchar_tab.html`
- `src/tgapp/web/templates/partials/process_response.html`
- `src/tgapp/web/templates/partials/plot_block.html`
- `src/tgapp/web/templates/partials/upload_status_block.html`
- `src/tgapp/web/templates/partials/heat_speed_block.html`
- `src/tgapp/web/templates/partials/summary_block.html`
- `src/tgapp/web/templates/partials/effect_block.html`

### Static assets
- `src/tgapp/web/static/styles.css`
- `src/tgapp/web/static/app.js`
- `src/tgapp/assets/styles.css`

---

## Important behavioral quirks from the original R app

These matter because future edits can easily break parity with the source app.

### UI/render pairing quirk
- In the R app, `output$heat.speed` uses `renderPrint(...)`.
- In `ui/ui.r`, it is rendered through `uiOutput("heat.speed")`.
- This mismatch is historical and should not be "cleaned up" casually unless both sides are intentionally normalized together.

### Upload/data expectations
- Upload flow expects thermogram CSV-like files from `input$thermogramm`.
- Saved app state is loaded from `.rds` via `input$data`.

### Misleading export naming
- Download labeled `downloadCsv` is not a true CSV export.
- In the R version it actually writes `saveRDS(data1(), file)` and uses `.tg` suffix.

### Report generation dependency gap
- The report download code references:
  - `report.Rnw`
  - `ckti.pdf`
- Those files were not present in the repository snapshot.
- Do not assume report generation is complete/usable without verifying those dependencies.

---

## Validation already performed

### Python compile/import checks used
- `uv run python -m compileall src`
- `uv run python -c "from tgapp.web.app import app; print(app.title); print(sorted(app.openapi()['paths'].keys()))"`

These were used as smoke checks.

### Browser/runtime observations already seen
- Main page loaded successfully at `http://127.0.0.1:8050/`
- Browser console showed only a `favicon.ico 404` during one smoke pass
- Static assets were observed returning `200`
- `POST /process` returned `200 OK`
- Earlier upload interactions produced repeated:
  - `POST /upload/thermograms HTTP/1.1" 422 Unprocessable Entity`

This means uploads and/or form wiring still need focused verification.

---

## Current unresolved work

### 1) Visual verification still needed
Need to verify the current first tab really behaves as intended:
- controls/settings on the left
- main graph on the right
- export/effect area placed appropriately under or near the graph
- compact desktop layout

### 2) Plotly rendering verification still needed
Need to confirm that `plot_payload_json` and frontend JS in `app.js` render the actual chart correctly in the current FastAPI template layout.

### 3) Upload flow still suspect
Earlier browser/server interaction showed `422 Unprocessable Entity` on thermogram upload routes.
This needs investigation in:
- form field names
- `multipart/form-data` wiring
- htmx submit behavior
- FastAPI parameter signatures

### 4) Local-only resource usage not yet confirmed
The user noticed some components may be loading from the internet.
This still needs explicit audit.

Need to check for:
- external CDN links in templates
- remote Plotly bundle source
- remote htmx source
- fonts/icons from external hosts
- any JS/CSS pulled via absolute URLs

Preferred end state: app works fully locally without internet dependency, unless intentionally documented otherwise.

### 5) Background run persistence
`uv run tgapp` works, but foreground runs stop when the shell session times out.
If persistent local execution matters, use a real background launch method and verify the server is still reachable.

---

## Deployment/runtime assumptions already introduced

- The Python app was prepared with subdirectory/reverse-proxy compatibility in mind.
- `root_path` / base path support matters and should be preserved.
- Session handling is cookie-backed.
- A session cookie name used in the Python app is:
  - `tgapp_session_id`
- Server-side session storage exists via infrastructure storage code.

When editing URLs or static asset paths, do not accidentally break base-path support.

---

## Files that are especially important for future work

### Source-of-truth R files
- `app.r`
- `ui/ui.r`
- `server/server.r`

### Python files likely to matter next
- `src/tgapp/application/view_models.py`
  - important because template context aliasing was already an issue
- `src/tgapp/web/routes/uploads.py`
  - likely place to debug 422 upload failures
- `src/tgapp/web/templates/partials/sidebar.html`
  - likely place to debug form field names and htmx wiring
- `src/tgapp/web/templates/partials/thermogram_tab.html`
  - main layout for controls vs graph
- `src/tgapp/web/static/styles.css`
  - main layout tuning and compact UI behavior
- `src/tgapp/web/static/app.js`
  - Plotly rendering and frontend interactions

---

## Reusable specialist session history

These were completed and reconciled previously. They are useful as historical context.

### Designer session
- Alias/session: `des-1 / ses_1011a695effeWeJh49ZxYvSCD5`
- Specialist: `designer`
- Objective: `Place controls beside graph`
- Outcome: completed and reconciled

Context it read included:
- `src/tgapp/web/static/styles.css`
- `src/tgapp/assets/styles.css`
- `src/tgapp/web/static/app.js`
- `src/tgapp/web/layout.py`
- `src/tgapp/web/templates/partials/sidebar.html`
- `ui/ui.r`
- `src/tgapp/web/templates/index.html`
- `src/tgapp/web/templates/partials/summary_tab.html`

### Fixer session
- Alias/session: `fix-1 / ses_100f65ac2ffeR9rFqJlrYH77u7`
- Specialist: `fixer`
- Objective: `Fix template context mismatch`
- Outcome: completed and reconciled

Context it read included:
- `src/tgapp/application/use_cases.py`
- `src/tgapp/web/templates/partials/sidebar.html`
- `src/tgapp/infrastructure/storage.py`
- `src/tgapp/infrastructure/file_parsers.py`
- `src/tgapp/web/deps.py`
- `src/tgapp/web/routes/processing.py`
- `src/tgapp/web/callbacks/processing.py`
- `src/tgapp/domain/models.py`

These sessions are not active now, but the notes explain why the current code may look the way it does.

---

## How to resume effectively after moving the project

1. Open the new project root.
2. Read these files first:
   - `AGENTS.md`
   - `AGENT_MEMORY.md`
   - `MIGRATION_HANDOFF.md`
3. Confirm the current root contains:
   - original R app files, or access to original app at `../tg.app`
   - `src/`
   - `src/tgapp/`
4. Start work from `src/tgapp/`, but compare behavior against:
   - `../tg.app/app.r`
   - `ui/ui.r`
   - `server/server.r`
5. Before changing layout or upload handling, inspect:
   - `src/tgapp/web/templates/partials/sidebar.html`
   - `src/tgapp/web/templates/partials/thermogram_tab.html`
   - `src/tgapp/web/static/styles.css`
   - `src/tgapp/web/static/app.js`
   - `src/tgapp/web/routes/uploads.py`

---

## Recommended next tasks

Recommended order:

1. Audit external dependencies in rendered HTML/CSS/JS and make the app fully local if possible.
2. Reproduce and fix `422 Unprocessable Entity` on upload routes.
3. Verify main Plotly graph rendering end-to-end.
4. Visually verify the compact first-tab layout.
5. Only then continue with polish or parity gaps.

---

## Things not to do

- Do not invent new app behavior without checking `server/server.r`.
- Do not casually refactor large parts of `server/server.r` parity logic into a different design unless necessary.
- Do not assume export/report features are complete.
- Do not break `root_path` / base-path support while simplifying routes or template URLs.
- Do not “clean up” weird output/render pairings from the R app unless the migration intentionally normalizes both sides together.

---

## Short summary for the next agent

This repository started as an R Shiny thermogram-processing app.
Work has already begun on a Python replacement in `src/tgapp/` using FastAPI + Jinja2 + htmx + Plotly.
Core processing logic has already been significantly ported.
The biggest remaining tasks are not architecture selection anymore; they are execution/parity tasks:
- verify/fix upload flow
- verify local-only assets
- verify Plotly rendering
- verify compact left-controls/right-graph layout

For behavior, trust the original R app.
For current implementation, continue from `src/tgapp/`.
