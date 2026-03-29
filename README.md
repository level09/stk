<p align="center">
  <img src="docs/logo.gif" alt="stk" width="480">
</p>

<h1 align="center">stk</h1>

<p align="center">
  <strong>Async Python framework with batteries you actually need.</strong><br>
  Auth, 2FA, WebAuthn, OAuth, WebSockets, admin dashboard, Vue 3 frontend. No build step, no third-party auth services. One codebase, you own everything.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet.svg" alt="uv"></a>
</p>

<p align="center">
  <a href="https://demo.stk.dev">Live Demo</a> &middot;
  <a href="https://docs.stk.dev">Docs</a> &middot;
  <a href="https://github.com/level09/stk/wiki">Tutorials</a>
</p>

---

```bash
git clone git@github.com:level09/stk.git && cd stk
./setup.sh                    # deps + secure .env
uv run quart create-db        # database via Alembic
uv run quart install          # admin user
uv run quart run              # localhost:5000
```

https://github.com/user-attachments/assets/a87bfad2-45dc-4d94-bdf1-0448dfea8084

## Why stk

Most frameworks give you routing and leave the rest as homework. Auth alone eats weeks. Then you bolt on Clerk or Auth0, hand your users' credentials to a third party, and pay per-MAU for the privilege.

stk ships what actually matters:

**You own your auth.** Registration, login, password recovery, session management, TOTP 2FA (Google Authenticator, Authy, 1Password), WebAuthn passkeys (Touch ID, YubiKey), recovery codes, OAuth (Google, GitHub). Production code, not a tutorial. Your users' data stays on your server.

**Async all the way down.** Quart + async SQLAlchemy + aiosmtplib + native WebSockets. Not async bolted onto a sync framework. Real concurrency without threads, workers, or callback hell.

**No JS build step.** Vue 3 + Vuetify 3 loaded directly in the browser. No webpack, no vite, no node_modules, no npm. Delete your frontend toolchain. Still get a polished admin dashboard with data tables, dark mode, collapsible sidebar, 5000+ icons.

**SQLite by default.** Deploy anywhere. No managed database required. PostgreSQL when you need it, not when the framework demands it.

**No Celery, no Redis (unless you want them).** Background tasks run on asyncio. Session store works with cookies or Redis. Complexity is opt-in.

> **Want payments?** [ReadyKit](https://readykit.dev) adds Stripe, multi-tenancy, and teams on top of stk.

## What's included

### Auth & Security
- Login, registration, password recovery, password change
- TOTP 2FA with QR code setup (authenticator apps)
- WebAuthn/passkeys as first factor or second factor
- Multi-factor recovery codes
- Google and GitHub OAuth with account linking
- Server-side session tracking (IP, browser, device, expiration)
- Account lockout after failed attempts
- Single-session mode (optional)
- Rate limiting on auth endpoints (sliding window, no Redis)
- PBKDF2-SHA512 password hashing, 12 char minimum

### Real-time
- Authenticated WebSocket endpoint with per-user message queues
- Broadcast to one user or all connected users
- Activity events pushed live to the dashboard
- Auto-reconnect on the frontend

### Admin Dashboard
- User management (CRUD, role assignment, activation)
- Role management with RBAC
- Activity audit log (every admin action, login from new IP, 2FA changes)
- Server-side paginated data tables
- JSON API endpoints for all admin operations

### Frontend
- Vue 3 + Vuetify 3 (zero build step)
- Dark/light theme with system preference detection
- Collapsible sidebar navigation
- Notification dropdown
- Tabler Icons (5000+)
- Custom `${ }` delimiters (no Jinja conflicts)

### Infrastructure
- Async email (aiosmtplib) with HTML + text templates
- Fire-and-forget background tasks (no Celery)
- CLI commands: create-db, db upgrade/downgrade/revision, install, create user, reset password, add role, cleanup sessions
- Docker Compose: PostgreSQL, Redis, Nginx (one command)
- VPS deploy script with auto-SSL via Caddy
- Pre-commit hooks, ruff linting
- Health endpoint (`/health`) for uptime monitoring

### AI-native
- Ships with Claude Code instructions (`CLAUDE.md`) and Windsurf rules
- AI-assisted scaffolding skills for blueprints, APIs, and migrations
- Your AI already knows the codebase conventions

## Stack

| Layer | Tech |
|-------|------|
| Runtime | Python 3.11+, [uv](https://docs.astral.sh/uv/) |
| Web | [Quart](https://quart.palletsprojects.com/) (async Flask) |
| ORM | SQLAlchemy 2.0+ async |
| Database | SQLite (default), PostgreSQL (optional) |
| Migrations | Alembic |
| Auth | [quart-security](https://quart-security.readthedocs.io/) (2FA, WebAuthn, OAuth) |
| Frontend | Vue 3, Vuetify 3, Axios |
| WebSockets | Native Quart WebSocket support |
| Email | aiosmtplib |
| Server | Uvicorn (ASGI) |
| Proxy | Nginx or Caddy |

## Configuration

Environment variables (`.env`):

```bash
SECRET_KEY=your_secret_key
QUART_APP=run.py
QUART_DEBUG=1                    # 0 in production

# PostgreSQL (optional, SQLite is default)
# SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://user:pass@localhost/dbname

# Redis sessions (optional, cookies are default)
# REDIS_URL=redis://localhost:6379/1

# OAuth (optional)
# GOOGLE_AUTH_ENABLED=true
# GOOGLE_OAUTH_CLIENT_ID=...
# GOOGLE_OAUTH_CLIENT_SECRET=...
# GITHUB_AUTH_ENABLED=true
# GITHUB_OAUTH_CLIENT_ID=...
# GITHUB_OAUTH_CLIENT_SECRET=...

# Email (optional)
# MAIL_SERVER=smtp.example.com
# MAIL_USERNAME=...
# MAIL_PASSWORD=...
# SECURITY_EMAIL_SENDER=noreply@example.com
```

Database migrations:

```bash
uv run quart create-db                        # upgrade to head
uv run quart db revision -m "add billing"    # generate a new revision
uv run quart db upgrade                       # apply migrations
uv run quart db downgrade -1                  # rollback one revision
uv run quart db stamp head                    # adopt Alembic for an existing DB
```

## Docker

```bash
docker compose up --build   # Redis, PostgreSQL, Nginx
```

## VPS Deploy

One command on any Ubuntu VPS:

```bash
curl -sSL https://raw.githubusercontent.com/level09/ignite/main/ignite.sh | sudo DOMAIN=your-domain.com bash
```

Handles Caddy (auto SSL), Python 3.13, Redis, systemd services. See [Ignite](https://github.com/level09/ignite).

## CLI Reference

```bash
uv run quart create-db              # Apply all migrations
uv run quart install                # Create admin user
uv run quart create                 # Create user by email/password
uv run quart add-role               # Assign role to user
uv run quart reset                  # Reset user password
uv run quart cleanup-sessions       # Deactivate expired sessions
uv run quart db upgrade [rev]       # Run migrations forward
uv run quart db downgrade <rev>     # Roll back migrations
uv run quart db revision -m "msg"   # Generate new migration
uv run quart db current             # Show current revision
uv run quart db history             # Show migration history
uv run quart migrate                # Alias for upgrade head
uv run quart migration-status       # Show current revision
uv run ruff check --fix . && uv run ruff format .  # Lint + format
uv run python checks.py             # Sanity checks
```

## License

MIT
