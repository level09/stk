<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/src/assets/logo-dark.webp">
    <img src="docs/src/assets/logo-light.webp" alt="stk" width="360">
  </picture>
</p>

<h1 align="center">stk</h1>

<p align="center">
  <strong>Async Python framework with batteries you actually need.</strong><br>
  Auth, 2FA, WebAuthn, OAuth, WebSockets, admin dashboard, Vue 3 frontend. No build step, no third-party auth services. One codebase, you own everything.
  STK makes SaaS apps legible, changeable, testable, and operable by agents.
</p>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.11%2B-blue.svg" alt="Python 3.11+"></a>
  <a href="https://docs.astral.sh/uv/"><img src="https://img.shields.io/badge/uv-package%20manager-blueviolet.svg" alt="uv"></a>
</p>

<p align="center">
  <a href="https://docs.stkit.dev">Docs</a> &middot;
  <a href="https://docs.stkit.dev/llms.txt">llms.txt</a> &middot;
  <a href="https://github.com/level09/stk/wiki">Tutorials</a>
</p>

---

```bash
uvx --from stkit stk init myapp && cd myapp
uv run stk db upgrade       # database via Alembic
uv run stk install          # admin user
uv run stk run              # localhost:5000
```

Your app is its own package that composes stk, not a fork of it. Upgrading stk is a version bump.

## Why stk

Most frameworks give you routing and leave the rest as homework. Auth alone eats weeks. Then you bolt on Clerk or Auth0, hand your users' credentials to a third party, and pay per-MAU for the privilege.

stk ships what actually matters:

**You own your auth.** Login, session management, TOTP 2FA (Google Authenticator, Authy, 1Password), WebAuthn passkeys (Touch ID, YubiKey), recovery codes, OAuth (Google, GitHub). Production code, not a tutorial. Your users' data stays on your server.

**Async all the way down.** Quart + async SQLAlchemy + aiosmtplib + native WebSockets. Not async bolted onto a sync framework. Real concurrency without threads, workers, or callback hell.

**No JS build step.** Vue 3 + Vuetify 4 loaded directly in the browser. No webpack, no vite, no node_modules, no npm. Delete your frontend toolchain. Still get a polished admin dashboard with data tables, dark mode, collapsible sidebar, 5000+ icons.

**SQLite by default.** Deploy anywhere. No managed database required. PostgreSQL when you need it, not when the framework demands it.

**No Celery, no Redis (unless you want them).** Background tasks run on asyncio. Session store works with cookies or Redis. Complexity is opt-in.

**Built to be operated by agents.** `stk inspect` reports routes, auth guards, models, and commands as JSON. `stk verify` and `stk smoke` are a real gate: lint, migration drift, and a real browser that fails on console errors and invisible text. The docs ship in the repo and the gate fails when they drift from the code.

> **Want payments?** [ReadyKit](https://readykit.dev) adds Stripe, multi-tenancy, and teams on top of stk.

## What's included

- **Auth and security:** Argon2id passwords (12 char minimum), TOTP 2FA, passkeys as first or second factor, recovery codes, Google and GitHub OAuth with PKCE and verified emails, session tracking by IP and device, account lockout, per-IP rate limits shared across workers, CSRF on every mutation. Public sign-up is off by default.
- **Admin dashboard:** users, roles, and an activity audit log, with server-paginated tables and JSON APIs.
- **Real-time:** authenticated, origin-checked WebSockets that push to a named user and close when the session ends.
- **Frontend:** Vue 3 and Vuetify 4 with no build step, dark mode, collapsible sidebar, notifications, Tabler Icons.
- **Tooling:** one CLI, `stk`: run, shell, new, db, doctor, verify, smoke, inspect, report, and user management.
- **Deploy:** a one-command VPS script (Caddy, systemd, hardened OS) or Docker Compose with PostgreSQL, Redis, and Nginx.

## Stack

| Layer | Tech |
|-------|------|
| Runtime | Python 3.11+, [uv](https://docs.astral.sh/uv/) |
| Web | [Quart](https://quart.palletsprojects.com/) (async Flask) |
| ORM | SQLAlchemy 2.0+ async |
| Database | SQLite (default), PostgreSQL (optional) |
| Migrations | Alembic |
| Auth | [quart-security](https://quart-security.readthedocs.io/) (2FA, WebAuthn, OAuth) |
| Frontend | Vue 3, Vuetify 4, Axios |
| Server | Uvicorn (ASGI) behind Caddy or Nginx |

## Documentation

Everything else lives at [docs.stkit.dev](https://docs.stkit.dev), and in this repo at `docs/src/content/docs/`:
[quick start](https://docs.stkit.dev/getting-started/), [build loop](https://docs.stkit.dev/build-loop/), [models](https://docs.stkit.dev/models/), [frontend](https://docs.stkit.dev/frontend/), [authentication](https://docs.stkit.dev/authentication/), [configuration](https://docs.stkit.dev/configuration/), [CLI reference](https://docs.stkit.dev/cli/), [deployment](https://docs.stkit.dev/deployment/), and [working with agents](https://docs.stkit.dev/ai-coding/). Upgrade notes are in `CHANGELOG.md`; the production security contract is `SECURITY.md`.

## License

MIT
