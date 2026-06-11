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

## Browser Feature Testing

For authenticated browser testing in development:

```bash
STK_ENV=development STK_ENABLE_AGENT_LOGIN=1 uv run quart browser-token create --user admin@example.com --ttl 60 --next /dashboard/
```

Open the returned `/_test/login?token=...` path in the browser. The route creates a normal authenticated session and redirects to the requested local path.

Use browser tests only for workflows where rendering, navigation, or interaction matters. Prefer API scenarios for CRUD and permission checks.
