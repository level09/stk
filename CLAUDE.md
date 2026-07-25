# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What is stk

Async Quart web framework with Vue 3 + Vuetify frontend (no build step). Full auth stack via quart-security (session auth, 2FA/TOTP, WebAuthn, OAuth). SQLite default, PostgreSQL optional. Alembic for migrations.

## Vision

stk is a lean agent-operable SaaS framework.

The goal is not to add AI features. The goal is to make the path from idea to secure working app cheaper, clearer, and more verifiable.

AI changed the cost curve: exploration, scaffolding, refactoring, and documentation are cheaper. Verification, security, judgment, and product taste are now the bottleneck. stk should optimize for that new center of gravity.

Core loop:

```text
idea -> scoped plan -> generated app surface -> inspect -> verify -> review -> ship
```

## Commands

Everything runs through one command, `stk`, grouped by purpose in `stk --help`.
It bakes in the app factory, so `QUART_APP` is never needed. `quart <command>`
still works for anything registered on `app.cli`.

```bash
./setup.sh                        # First-time setup (venv, deps, .env)
uv sync --extra dev               # Install with dev tools
uv run stk --help                 # Command map, grouped by purpose
uv run stk run                    # Dev server at localhost:5000
uv run stk run --port 5001        # Alt port (macOS 5000 conflict)
uv run stk create-db              # Apply all migrations (upgrade to head)
uv run stk install                # Create admin user
uv run ruff check --fix . && uv run ruff format .  # Lint + format
uv run python checks.py           # Sanity checks (not pytest)
docker compose up --build         # Full stack (Redis, PostgreSQL, Nginx)
```

Drop the `uv run` prefix by activating the venv once per shell:
`source .venv/bin/activate`, then `stk run`, `stk shell`, `stk verify`.

### Agent Operability

Prefer these over guessing from files. Structured agent context lives in `.stk/context/` (architecture, commands, verification, frontend).

```bash
uv run stk inspect routes --json   # Route map with auth and source info
uv run stk inspect context --json  # Routes + models in one contract
uv run stk doctor                  # Environment/app state, each line with its fix
uv run stk verify --watch          # Re-run affected checks on every save
uv run stk verify --json           # Lint, sanity, migration checks (exit 0/1)
uv run stk smoke --json            # Real-browser behavioral check (Playwright)
uv run stk report                 # Static project review artifact
uv run stk shell                  # Async REPL: app, live db session, models, top-level await (ptpython)
uv run stk shell -c "await count(User)"  # One-shot query, prints last expression
uv run stk new <module>            # Scaffold + migrate, ends at a URL you can open
uv run python -m unittest discover -s tests
```

### Database Migrations (Alembic)

```bash
uv run stk db upgrade [revision]              # Apply migrations (default: head)
uv run stk db downgrade <revision>            # Rollback (e.g. -1 for one step)
uv run stk db revision -m "description"       # Autogenerate new revision
uv run stk db revision -m "desc" --empty      # Empty revision for manual SQL
uv run stk db current                         # Show current revision
uv run stk db history                         # Show migration history
uv run stk db stamp head                      # Adopt Alembic on existing DB
uv run stk db check                           # Fail if models drifted from migrations
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

Sync click commands wrapping `asyncio.run()` live in the `stk/cli/` package: `agent.py` (inspect, verify, smoke, report, shell, new), `database.py` (create-db, db group, migration drift), `users.py` (install, create, add-role, reset, sessions, browser-token), plus `reports.py` and `smoke.py` for the machine-readable builders behind them. Quart CLI doesn't support async click commands. All commands re-exported from `stk/cli/__init__.py` are auto-registered via `register_commands()` in `app.py`.

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
- Recovery codes (3 codes, hashed at rest, displayed only once at generation)
- Session freshness: 60-minute window, enforced on 2FA/recovery/passkey management routes (stale session gets 401)
- Logout is POST-only (`layoutMixin.logout()` submits the form; plain links 405)

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

Vue 3 + Vuetify loaded from static files (no build step). **Options API** (`data()`, `methods`, `mounted()`), NOT Composition API. Versions are pinned in `stk/static/VERSIONS.txt` and refreshed with `./vendor.sh`; see `.stk/context/frontend.md` before bumping Vuetify.

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
