# Commands

Use `uv` for Python commands.

Common commands:
- `uv run quart run`
- `uv run quart create-db`
- `uv run quart db current`
- `uv run quart db history`
- `uv run ruff check .`
- `uv run ruff format .`
- `uv run python checks.py`
- `uv sync --extra dev`
- `uv run playwright install chromium`

Agent-operability commands:
- `uv run quart inspect routes --json`
- `uv run quart inspect context --json`
- `uv run quart verify` (ruff + checks.py + migration drift)
- `uv run quart verify --json`
- `uv run quart smoke`
- `uv run quart smoke --json`
- `uv run quart report`
- `uv run quart shell` (async REPL: app, live `db` session, all models, top-level await; ptpython gives highlighting and completion when the dev extra is installed)
- `uv run quart shell -c "await count(User)"` (one-shot query, prints the last expression)

Run `uv run quart smoke` for frontend-touching changes. It is the behavioral browser check for this no-build Vue/Vuetify frontend.
