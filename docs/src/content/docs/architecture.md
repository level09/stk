---
title: "Architecture"
description: "How an stk app is laid out, and where each request goes"
---

## Project Structure

```
stk/
├── stk/                  # Main application package
│   ├── app.py            # Application factory, blueprint registration
│   ├── settings.py       # Configuration
│   ├── extensions.py     # Async SQLAlchemy engine, session factory, Base
│   ├── migrations.py     # Alembic config behind `stk db`
│   ├── security.py       # csrf_exempt for webhooks
│   ├── cli/              # CLI commands (agent, database, users, doctor, smoke, reports)
│   ├── scaffold/         # Templates behind `stk new`
│   ├── shell.py          # Async REPL behind `stk shell`
│   ├── tasks/            # Async background tasks
│   ├── websocket.py      # WebSocket blueprint
│   ├── portal/           # Blueprint: protected dashboard
│   ├── public/           # Blueprint: public routes, OAuth callbacks
│   ├── user/             # Blueprint: admin user/role/activity management, models
│   ├── utils/            # Email, rate limiting
│   ├── static/           # Vue, Vuetify, Axios, Tabler Icons, app JS and CSS
│   └── templates/        # Jinja2 templates
├── alembic/              # Migration env and versions/
├── tests/                # unittest suite
├── checks.py             # Sanity checks run by `stk verify`
├── docs/                 # This site; pages in docs/src/content/docs/
├── instance/             # SQLite database
├── .claude/skills/       # Agent procedures (also at .agents/skills)
├── CLAUDE.md             # Agent index and rules (AGENTS.md links here)
├── pyproject.toml        # Dependencies and project config
├── setup.sh              # Setup script
├── run.py                # ASGI entry point
└── docker-compose.yml    # Docker configuration
```

## Blueprints

`register_blueprints()` in `stk/app.py` registers four blueprints: `users`, `public`, `portal`, and the `ws` WebSocket blueprint. Login, registration, 2FA, and passkey pages come from quart-security itself.

### Portal (`portal/`)

The protected dashboard. A blueprint-level `before_request` requires a session for every route:

```python
from quart import Blueprint, render_template
from quart_security import auth_required

portal = Blueprint("portal", __name__, static_folder="../static")

@portal.before_request
@auth_required("session")
async def before_request():
    pass

@portal.route("/dashboard/")
async def dashboard():
    return await render_template("dashboard.html")
```

### User (`user/`)

Admin pages and JSON APIs for users, roles, and activity (`/users/`, `/roles/`, `/activities/`). The whole blueprint requires an admin:

```python
bp_user = Blueprint("users", __name__, static_folder="../static")

@bp_user.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass
```

It also holds the models (`stk/user/models.py`) and the auth signal handlers that track sessions and log password and 2FA changes.

### Public (`public/`)

Unauthenticated routes: the landing page, `/health`, `robots.txt`, and the Google and GitHub OAuth callbacks.

```python
public = Blueprint("public", __name__, static_folder="../static")

@public.route("/")
async def index():
    return await render_template("index.html")
```

To add a module of your own, run `uv run stk new <module>`. It scaffolds the blueprint, model, templates, and migration, and ends at a URL you can open.

## Request lifecycle

Each request gets its own database session on `g.db_session`, opened in `before_request` and closed in `after_request` (`stk/app.py`). CLI code and background tasks have no request, so they open their own session from `stk.extensions.async_session_factory`. See [Models and Queries](/models).
