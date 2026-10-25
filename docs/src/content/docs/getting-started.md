---
title: "Quick Start"
description: "Get up and running with stk"
sidebar:
  label: "Quick Start"
---

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (fast Python package manager)

Optional: Redis (session store) and PostgreSQL (SQLite works by default). Both drivers come with `uv sync --extra full`.

## Start an app

stk is a package; your app is a separate, thin package that composes it. `stk init` writes one, with a `.env` of fresh secrets:

```bash
uvx --from git+https://github.com/level09/stk stk init myapp
cd myapp
uv run stk db upgrade     # stk's migrations, then the app's
uv run stk install        # Create admin user
uv run stk run            # Start server (--port 5001 if macOS holds 5000)
```

Visit `http://localhost:5000` to see your application: sign-in, two-factor, passkeys, user and role admin, and a dashboard, before you write a line.

The app depends on stk through `[tool.uv.sources]`, pinned to a release tag. `stk init --source <path>` installs stk from a local checkout or wheel instead, for working on stk itself.

To drop the `uv run` prefix, activate the venv once per shell with `source .venv/bin/activate`, then run `stk run`, `stk shell`, `stk verify`. `uv run stk --help` lists every command, grouped by purpose. Every command finds the app from `[tool.stk] app` in the nearest `pyproject.toml` (override with `STK_APP=package.app:app`).

Anything unclear about the state of your app? One command answers it:

```bash
uv run stk doctor       # env file, app, secrets, database, migrations, admin, assets, browser
```

`stk smoke` needs a browser for Playwright. If doctor flags it, run `uv run playwright install chromium`.

Then read [The Build Loop](/build-loop) for the scaffold, watch, and verify cycle, and [Architecture](/architecture) for how the app composes stk.

## Docker Setup

`stk init` also writes the production stack, `Dockerfile` and `docker-compose.yml` with Redis, PostgreSQL, and Nginx:

```bash
docker compose up --build
```

The stack refuses to start until `.env` sets the database and Redis passwords, `STK_HOST`, `TLS_CERTIFICATE`, and `TLS_PRIVATE_KEY` (see the Docker block in the app's `.env-sample` and [Deployment](/deployment)).

## Environment Configuration

`stk init` copies `.env-sample` to `.env` and fills in `SECRET_KEY` and `SECURITY_PASSWORD_SALT`. Key variables:

```bash
SECRET_KEY=your_secret_key
SECURITY_PASSWORD_SALT=your_salt
QUART_DEBUG=1                    # 0 in production
STK_ENV=development              # defaults to production when unset
SECURITY_REGISTERABLE=False      # public password registration is off by default

# PostgreSQL (optional, SQLite at instance/stk.db by default)
# SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://user:pass@localhost/dbname

# Redis session store (optional, needs: uv sync --extra full)
# REDIS_URL=redis://localhost:6379/1
```

Settings the app adds go on its own `Config`, a subclass of `stk.Config` in `myapp/settings.py`. See [Configuration](/configuration).

## Working on stk itself

Clone the repository and run `./setup.sh`: it installs the dev dependencies and writes a `.env`. Inside the repository, every command runs the bundled example app in `examples/minimal`, named by `[tool.stk]` in stk's own `pyproject.toml`.

## Next Steps

- [Build Loop](/build-loop): doctor, scaffold, watch, smoke
- [Shell](/shell): async REPL with your models loaded
- [Architecture](/architecture): the app package, extensions, and blueprints
- [Models and Migrations](/models): async SQLAlchemy and Alembic
- [Frontend](/frontend): Vue and Vuetify with no build step
- [Authentication](/authentication): user management and OAuth setup
- [Deployment](/deployment): production deployment
