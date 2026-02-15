# stk

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**[Live Demo](https://demo.stk.dev)** · **[Docs](https://docs.stk.dev)** · **[Tutorials](https://github.com/level09/stk/wiki)**

A full-stack async Python framework. Auth, 2FA, WebSockets, admin dashboard, Vue 3 frontend. No build step, no third-party auth services, no JS toolchain. One codebase, you own everything.

```bash
git clone git@github.com:level09/stk.git && cd stk
./setup.sh                    # deps + secure .env
uv run quart create-db        # database
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
- Single-session mode (optional)
- Rate limiting on auth endpoints (sliding window, no Redis)
- PBKDF2-SHA512 password hashing

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
- Tabler Icons (5000+) and Material Design Icons
- Custom `${ }` delimiters (no Jinja conflicts)

### Infrastructure
- Async email (aiosmtplib) with HTML + text templates
- Fire-and-forget background tasks (no Celery)
- CLI commands: create-db, install, create user, reset password, add role, cleanup sessions
- Docker Compose: PostgreSQL, Redis, Nginx (one command)
- VPS deploy script with auto-SSL via Caddy
- Pre-commit hooks, ruff linting
- Sanity checks (`uv run python checks.py`) instead of test theater

### AI-native
- Ships with Claude Code instructions (CLAUDE.md) and Cursor rules
- Detailed agent patterns (AGENTS.md) for AI-assisted development
- Your AI already knows the codebase conventions

## Stack

| Layer | Tech |
|-------|------|
| Runtime | Python 3.11-3.13, [uv](https://docs.astral.sh/uv/) |
| Web | Quart (async Flask) |
| ORM | SQLAlchemy 2.0+ async |
| Database | SQLite (default), PostgreSQL (optional) |
| Auth | quart-security (2FA, WebAuthn, OAuth) |
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

# PostgreSQL (optional)
# SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://user:pass@localhost/dbname

# Redis sessions (optional)
# REDIS_URL=redis://localhost:6379/1

# OAuth (optional)
# GOOGLE_AUTH_ENABLED=true
# GOOGLE_OAUTH_CLIENT_ID=...
# GOOGLE_OAUTH_CLIENT_SECRET=...
# GITHUB_AUTH_ENABLED=true
# GITHUB_OAUTH_CLIENT_ID=...
# GITHUB_OAUTH_CLIENT_SECRET=...
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

## License

MIT
