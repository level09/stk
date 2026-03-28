# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is stk

Async Quart web framework with Vue 3 + Vuetify frontend (no build step). Full auth stack via quart-security (session auth, 2FA/TOTP, WebAuthn, OAuth). SQLite default, PostgreSQL optional. Alembic for migrations.

## Commands

```bash
./setup.sh                        # First-time setup (venv, deps, .env)
uv sync --extra dev               # Install with dev tools
uv run quart run                  # Dev server at localhost:5000
uv run quart run --port 5001      # Alt port (macOS 5000 conflict)
uv run quart create-db            # Apply all migrations (upgrade to head)
uv run quart install              # Create admin user
uv run ruff check --fix . && uv run ruff format .  # Lint + format
uv run python checks.py           # Sanity checks (not pytest)
docker compose up --build          # Full stack (Redis, PostgreSQL, Nginx)
```

### Database Migrations (Alembic)

```bash
uv run quart db upgrade [revision]              # Apply migrations (default: head)
uv run quart db downgrade <revision>            # Rollback (e.g. -1 for one step)
uv run quart db revision -m "description"       # Autogenerate new revision
uv run quart db revision -m "desc" --empty      # Empty revision for manual SQL
uv run quart db current                         # Show current revision
uv run quart db history                         # Show migration history
uv run quart db stamp head                      # Adopt Alembic on existing DB
```

Migration config lives in `stk/migrations.py`. Alembic env in `alembic/env.py`. Revisions in `alembic/versions/`. SQLite uses batch mode automatically for ALTER TABLE support.

## Architecture

### Async SQLAlchemy (not flask-sqlalchemy)

Engine and session factory live in `stk/extensions.py` as module-level globals (`ext.engine`, `ext.async_session_factory`). No `db` object. Models inherit from `Base` (plain `DeclarativeBase`), not `db.Model`.

Request-scoped sessions via `g.db_session`, created in `before_request`, closed in `after_request` (see `stk/app.py`).

```python
# In request handlers: use g.db_session
from quart import g
from sqlalchemy import select
result = await g.db_session.execute(select(User).where(User.active == True))
users = result.scalars().all()

# In CLI commands: use ext.async_session_factory directly
import stk.extensions as ext
async with ext.async_session_factory() as session:
    ...
```

All relationships must use `lazy="selectin"` for async compatibility.

### CLI Commands

Sync click commands wrapping `asyncio.run()` in `stk/commands.py`. Quart CLI doesn't support async click commands. The `db` group is a click.Group with Alembic subcommands. All commands are auto-registered via `register_commands()` in `app.py`.

### Blueprints

- `stk/public/` - unauthenticated routes, OAuth callbacks (Google, GitHub)
- `stk/user/` - auth, login, registration, OAuth, WebAuthn, 2FA, session management
- `stk/portal/` - protected dashboard (blueprint-level `@auth_required`)
- `stk/websocket.py` - WebSocket blueprint (releases DB session early for long-lived connections)

### Auth (quart-security)

`SQLAlchemyUserDatastore` with session factory callable (`lambda: g.db_session`). Key decorators: `@auth_required("session")`, `@roles_required('admin')`.

**Features enabled:**
- Session auth with tracking (IP, device, browser via `Session` model)
- 2FA via TOTP authenticator (`SECURITY_TWO_FACTOR = True`)
- WebAuthn as first or multi-factor (`SECURITY_WEBAUTHN = True`)
- OAuth (Google, GitHub) via AuthLib `AsyncOAuth2Client`
- Password hashing: pbkdf2_sha512, min 12 chars
- Account lockout: `failed_login_count` + `locked_until` on User model
- Recovery codes (3 codes)
- Session freshness: 60-minute window

**Signal handlers** (all async, in `stk/user/views.py`):
- `@user_authenticated.connect` - creates session record, tracks IP changes
- `@user_logged_out.connect` - deactivates session
- `@password_changed.connect` - logs change, marks password as user-set
- `@tf_profile_changed.connect` - logs 2FA modifications

**Rate limiting** on auth endpoints (login, register, reset, confirm): 10 req/60s per IP. In-memory sliding window in `stk/utils/ratelimit.py`.

### Models (`stk/user/models.py`)

- **User** - UserMixin. Auth fields, login tracking, lockout, 2FA, WebAuthn handle. Methods: `from_dict()`, `to_dict()`, `random_password()`, `logout_other_sessions()`, `get_active_sessions()`.
- **Role** - RoleMixin. Many-to-many with User via `roles_users`.
- **WebAuthn** - credential storage, FK to User via `fs_webauthn_user_handle`.
- **OAuth** - provider accounts linked to users. Unique on `(provider, provider_user_id)`.
- **Activity** - audit log. `register()` logs + broadcasts via WebSocket.
- **Session** - tracks active sessions with IP, device meta, expiry.

### Background Tasks

No Celery. `stk/tasks.py` provides:
- `run_in_background(coro)` - fire-and-forget with exception logging
- `run_with_session(coro_factory)` - provides fresh DB session to coroutine
- `cleanup_expired_sessions()` - deactivates expired, deletes 30+ day old records

### Frontend

Vue 3 + Vuetify loaded from static files (no build step). **Options API** (`data()`, `methods`, `mounted()`), NOT Composition API.

- **Delimiters:** `${}` via `config.delimiters` (avoids Jinja `{{}}` conflicts)
- **Layout mixin:** Every app uses `mixins: [layoutMixin]` for drawer, nav, WebSocket, notifications
- **Component registration:** Call `registerStkComponents(app)` before `.mount('#app')`
- **Vuetify init:** `createVuetify(config.vuetifyConfig)` (config is in `static/js/config.js`)
- **Icons:** Tabler Icons (`ti ti-pencil`, `ti ti-plus`, etc.), NOT Material Design Icons
- **Server data:** Pass via `<script type="application/json" id="...">{{ data|tojson|safe }}</script>`
- **Navigation:** Sidebar entries in `static/js/navigation.js` with `role: 'admin'` for access control
- **JSON responses:** List endpoints use `orjson` via `import orjson as json` and `Response(json.dumps(data), content_type="application/json")`
- **Request body:** Frontend sends mutations as `{item: {...}}`, extract with `json_data.get("item", {})`

## Key Gotchas

- `User.from_dict()`, `Activity.register()`, `Session.create_session()` are all async.
- Signal handlers (`@user_authenticated.connect` etc.) are async.
- Pagination is manual: `offset().limit()` + `select(func.count())`.
- WebSocket connections release their DB session early to avoid pool starvation.
- Session backend: Redis if `REDIS_URL` is set, otherwise cookie-based.
- `DISABLE_MULTIPLE_SESSIONS` config controls single-session enforcement.
