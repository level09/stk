---
title: "Architecture"
description: "How an stk app is laid out, and where each request goes"
---

## An app composes stk

stk is an installed package. An app is a separate package that composes it and never edits a framework file, so upgrading stk is a version bump. `stk init myapp` writes this shape:

```
myapp/
├── pyproject.toml        # depends on stk; [tool.stk] app = "myapp.app:app"
├── .env                  # secrets, never committed
├── CLAUDE.md, .claude/   # agent index (AGENTS.md links to it) and stk's skills
├── myapp/
│   ├── app.py            # the composition (below)
│   ├── settings.py       # class Config(stk.Config)
│   ├── templates/        # found before stk's (optional)
│   ├── static/           # found before stk's (optional)
│   ├── migrations/       # the app's Alembic lineage (stk new creates it)
│   └── note/             # an extension, written by `stk new note`
│       ├── __init__.py   # init_app(app): blueprint, sidebar entry
│       ├── models.py
│       ├── views.py
│       └── templates/note/index.html
├── tests/
├── .github/workflows/     # CI: tests, verify, smoke
├── Dockerfile, docker-compose.yml, nginx/, postgres/
└── instance/             # SQLite database, shell history
```

```python
# myapp/app.py
from stk import Stk

from myapp import note
from myapp.settings import Config

# Each extension is a package with init_app(app); order is precedence.
extensions = [note]

app = Stk(__name__, config=Config, extensions=extensions)
```

`Stk` is a Quart app. It builds stk's core (database, auth, CSRF, rate limits, error pages, the blueprints below), then takes each extension in list order: imports its `models` module if it has one, so migrations see its tables, and calls its `init_app(app)`. An extension registers what it needs with plain Quart: `app.register_blueprint`, `app.cli.add_command`, `app.errorhandler`. It adds a sidebar page with `app.navigation.append({...})`.

Templates and static files resolve app first, then each extension's folder in list order, then stk's. An app overrides any core template by putting a file at the same path, and reaches the original as `stk/<name>`, so an override can extend it:

```html
{# myapp/templates/layout.html #}
{% extends "stk/layout.html" %}
{% block title %}{{ config.APP_NAME }}: notes{% endblock %}
```

Path override is for templates and static files only. Python code is never overridden: stk's security code stays importable and is fixed for every app by an upgrade.

Core models (User, Role, WebAuthn, OAuth, sessions, activity, security state) are fixed. Apps attach their own tables by foreign key to `user.id` or a profile table.

## Inside stk

```
stk/
├── app.py            # Stk, core registration, static versioning, navigation
├── settings.py       # Config and TestingConfig
├── extensions.py     # Async SQLAlchemy engine, session factory, Base
├── migrations/       # Alembic env and stk's own revisions (versions/)
├── security.py       # csrf_exempt for webhooks
├── checks.py         # Sanity checks run by `stk verify`
├── cli/              # Commands behind `stk` (develop, agent, database, users, doctor, smoke)
├── scaffold/         # `stk init` app template and `stk new` module templates
├── shell.py          # Async REPL behind `stk shell`
├── tasks/            # Async background tasks
├── websocket.py      # WebSocket blueprint
├── portal/           # Blueprint: protected dashboard
├── public/           # Blueprint: public routes, OAuth callbacks
├── user/             # Blueprint: admin user/role/activity management, models
├── utils/            # Email, rate limiting
├── static/           # Vue, Vuetify, Axios, Tabler Icons, app JS and CSS
└── templates/        # Jinja2 templates
```

The repository also holds `examples/minimal` (the app the repository runs, and the shape `stk init` writes plus one extension), `tests/`, `docs/`, and `.claude/skills/`.

## Blueprints

`register_blueprints()` in `stk/app.py` registers stk's four blueprints: `users`, `public`, `portal`, and the `ws` WebSocket blueprint. Login, registration, 2FA, and passkey pages come from quart-security itself.

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

To add a module of your own, run `uv run stk new <module>`. It writes an extension into your app package (blueprint, model, template, sidebar entry), adds it to `extensions`, generates and applies its migration, and ends at a URL you can open.

## Request lifecycle

Each request gets its own database session on `g.db_session`, opened in `before_request` and closed in `after_request` (`stk/app.py`). Extension blueprints share it. CLI code and background tasks have no request, so they open their own session from `stk.extensions.async_session_factory`. See [Models and Queries](/models).
