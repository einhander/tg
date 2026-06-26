# tg.app migration handoff

## Что это
- Исходный проект: маленькое **R Shiny** приложение.
- Реальный entrypoint исходника: `app.r`.
- UI берётся из `ui/ui.r`, серверная логика из `server/server.r`.
- Основная логика исходного приложения живёт в `server/server.r`.
- Исходное приложение сейчас доступно по относительному пути `../tg.app`.

## Что уже сделали
- Разобрали структуру R-приложения.
- Добавили `AGENTS.md` с repo-specific заметками.
- Создали новую Python-версию в папке `python-app/`.
- Выбрали стек: **FastAPI + Jinja2 + htmx + Plotly**.
- Сохранили layered-архитектуру Python-версии:
  - `domain/`
  - `application/`
  - `infrastructure/`
  - `web/`
- Перенесли значимую вычислительную логику из R в Python:
  - resampling по `bins`
  - adjusted `difflag`
  - mean traces
  - `dmdt`
  - correction по `deltatemp`
  - heat speed
  - effect calculation
  - DTA/DTG peak overlays
- Собрали FastAPI routes для загрузок, processing, effect и export.
- Исправили минимум две runtime-проблемы:
  - `TemplateResponse()` без `request`
  - template context mismatch: `'session_state' is undefined`
- Перестроили UI в компактный 3-tab layout.

## Текущая цель
Доделать Python-версию как замену R Shiny UI, сохранив уже перенесённую логику.

## UI-решения, которые уже выбраны
- Не Dash.
- Нужен **Shiny-like / internal-tool** вид.
- 3 верхних вкладки:
  - `Настройки`
  - `Деконволюция`
  - `Debug`
- На первом экране настройки должны быть **слева**, основной график **справа**.
- Нужна совместимость с запуском в поддиректории / за reverse proxy (`root_path` / base path support).

## Что ещё не добито
- Визуально проверить, что первый tab действительно держит layout "контролы слева, график справа".
- Проверить, что Plotly график рендерится корректно в текущем шаблоне.
- Разобраться с upload/form проблемами, где ранее были `422 Unprocessable Entity`.
- Проверить, не тянутся ли внешние ресурсы из интернета; приложение желательно держать локальным.

## Важные наблюдения
- `app.r` сразу делает `runApp(tg)`, так что sourcing исходного файла запускает приложение.
- `ui/ui.r` — это `tabPanel(...)`, а не полный `fluidPage()`.
- В исходнике есть глобальное состояние через `values <- reactiveValues(...)`.
- `output$heat.speed` в R использует `renderPrint(...)`, а в UI рендерится через `uiOutput("heat.speed")` — это историческая особенность, ломать без причины не надо.
- Upload thermogram ожидает CSV-подобные файлы через `input$thermogramm`.
- Загружаемое/сохраняемое состояние — `.rds`.
- Кнопка/экспорт `downloadCsv` в R по факту пишет `saveRDS(...)`, это не настоящий CSV export.
- Код report generation ссылается на `report.Rnw` и `ckti.pdf`, но этих файлов в snapshot нет.

## Где смотреть в первую очередь
- Исходник:
  - `../tg.app/app.r`
  - `../tg.app/ui/ui.r`
  - `../tg.app/server/server.r`
- Новая Python-версия:
  - `pyproject.toml`
  - `src/tgapp/main.py`
  - `src/tgapp/config.py`
  - `src/tgapp/application/use_cases.py`
  - `src/tgapp/application/view_models.py`
  - `src/tgapp/application/session_state.py`
  - `src/tgapp/application/dto.py`
  - `src/tgapp/domain/processing.py`
  - `src/tgapp/domain/summary.py`
  - `src/tgapp/domain/peaks.py`
  - `src/tgapp/domain/models.py`
  - `src/tgapp/infrastructure/storage.py`
  - `src/tgapp/infrastructure/file_parsers.py`
  - `src/tgapp/infrastructure/plotting.py`
  - `src/tgapp/infrastructure/serialization.py`
  - `src/tgapp/web/app.py`
  - `src/tgapp/web/app_factory.py`
  - `src/tgapp/web/layout.py`
  - `src/tgapp/web/routes/uploads.py`
  - `src/tgapp/web/routes/processing.py`
  - `src/tgapp/web/routes/effects.py`
  - `src/tgapp/web/routes/exports.py`
  - `src/tgapp/web/callbacks/uploads.py`
  - `src/tgapp/web/callbacks/processing.py`
  - `src/tgapp/web/callbacks/plots.py`
  - `src/tgapp/web/callbacks/exports.py`
  - `src/tgapp/web/templates/index.html`
  - `src/tgapp/web/templates/base.html`
  - `src/tgapp/web/templates/partials/thermogram_tab.html`
  - `src/tgapp/web/templates/partials/sidebar.html`
  - `src/tgapp/web/templates/partials/process_response.html`
  - `src/tgapp/web/static/styles.css`
  - `src/tgapp/web/static/app.js`

## Команды, которые уже использовались
- Проверка компиляции Python-кода:
  - `uv run python -m compileall src`
- Smoke check app/imports:
  - `uv run python -c "from tgapp.web.app import app; print(app.title); print(sorted(app.openapi()['paths'].keys()))"`
- Локальный запуск:
  - `uv run tgapp`

## Что помнить при переносе папки проекта
- Этот файл должен ехать вместе с проектом.
- После переноса ориентироваться на относительные пути от нового корня проекта.
- Если сломаются временные/логовые пути, они не критичны; главное — исходник в `../tg.app` и текущая Python-структура `src/tgapp/`.

## Кратко: с чем продолжать работу
1. Открыть корень проекта и перейти к `src/tgapp/`.
2. Проверить текущий FastAPI UI.
3. Дожать локальность ресурсов, upload flows и layout первого таба.
4. Сверять поведение с `../tg.app/server/server.r` и `../tg.app/ui/ui.r`, а не придумывать новую логику.
