# Verification

Use the smallest verification set that catches the risk introduced by the change.

Default checks:
- `uv run python -m unittest tests/test_agent_operability.py`
- `uv run ruff check .`
- `uv run python checks.py`
- `uv run quart verify`

For database changes, also run:
- `uv run quart db current`
- `uv run quart db history`

For auth or route changes, also run:
- `uv run quart inspect routes --json`
- `uv run quart report`
