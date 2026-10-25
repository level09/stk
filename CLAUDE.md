# CLAUDE.md

Guidance for coding agents working in this repository. `AGENTS.md` is a symlink to this file.

stk is an installed package. An app is a separate package made by `stk init`: `myapp/app.py` builds `Stk(__name__, config=Config, extensions=[...])`, each extension is a package with `init_app(app)`, and the app never edits a stk file. This repository runs its bundled example app, `examples/minimal`.

## What is stk

Async Quart web framework with a Vue 3 + Vuetify frontend and no build step. Full auth stack via quart-security (session auth, 2FA/TOTP, WebAuthn, OAuth). SQLite by default, PostgreSQL optional, Alembic for migrations.

stk is a lean agent-operable SaaS framework. The goal is not to add AI features; it is to make the path from idea to secure working app cheaper, clearer, and more verifiable. Exploration and scaffolding are cheap now. Verification, security, judgment, and product taste are the bottleneck, and stk optimizes for them:

```text
idea -> scoped plan -> generated app surface -> inspect -> verify -> review -> ship
```

## Where truth lives

1. **The running code.** Ask it before reading files: `uv run stk inspect context --json` (routes with auth, models), `uv run stk inspect commands --json` (every command and option), `uv run stk doctor` (app state, each problem with its fix). `uv run stk new <module>` writes the canonical CRUD extension into the app; copy its patterns.
2. **The docs**, in `docs/src/content/docs/`, published at https://docs.stk.dev (with `/llms.txt`). Read the page for your task before writing code:

| Task | Page |
|---|---|
| Setup, `.env`, first run | `docs/src/content/docs/getting-started.md` |
| doctor, scaffold, watch, smoke, which checks a change needs, test login | `docs/src/content/docs/build-loop.md` |
| Async REPL against the real app | `docs/src/content/docs/shell.md` |
| App package, extensions, overrides, blueprints, request lifecycle | `docs/src/content/docs/architecture.md` |
| Models, queries, migrations, SQLite traps | `docs/src/content/docs/models.md` |
| JSON endpoints, error conventions, webhooks | `docs/src/content/docs/api.md` |
| Vue/Vuetify pages, components, navigation | `docs/src/content/docs/frontend.md` |
| Background tasks, WebSocket push | `docs/src/content/docs/background-work.md` |
| Auth, 2FA, passkeys, OAuth, CSRF, rate limits | `docs/src/content/docs/authentication.md` |
| Renaming the product | `docs/src/content/docs/branding.md` |
| How agents work in stk | `docs/src/content/docs/ai-coding.md` |
| Every environment variable and config key | `docs/src/content/docs/configuration.md` |
| Every command and option (generated) | `docs/src/content/docs/cli.md` |
| Production, Docker, upgrading stk in an app | `docs/src/content/docs/deployment.md` |
| Production security contract | `SECURITY.md` |

3. **Skills** in `.claude/skills/` (mirrored at `.agents/skills/`) hold procedures: `stk-blueprint`, `stk-api`, `stk-migrate`, `stk-deploy`, and `stk-lessons` (when a gotcha the docs missed costs you time, log one line in `.stk/lessons.md`).

When you change behavior, update its docs page in the same commit. `cli.md` is generated: rerun `uv run stk inspect commands --markdown > docs/src/content/docs/cli.md`. `stk verify` fails when docs name commands, flags, settings, or files the code lacks, or when this index misses a page.

## Commands

Everything runs through `stk` (`uv run stk --help` for the grouped map). It finds the app from `[tool.stk] app` in the nearest `pyproject.toml`.

```bash
uv run stk init <name>              # New app package with fresh secrets
./setup.sh                          # Working on stk itself: deps and .env
uv run stk run                      # Dev server at localhost:5000 (--port 5001 on macOS)
uv run stk db upgrade               # stk's migrations, then the app's
uv run stk install                  # Create admin user
uv run stk doctor                   # What is wrong, and the command that fixes it
uv run stk new <module>             # Extension + migration, ends at a URL
uv run stk verify --watch           # Re-run affected checks on every save
uv run stk verify --json            # Lint, sanity, migration drift (exit 0/1)
uv run stk smoke --json             # Real-browser behavioral check
uv run stk shell -c "await count(User)"   # One-shot query against the real app
uv run stk db revision -m "desc"    # Autogenerate in the app's lineage, then: uv run stk db upgrade
uv run ruff check --fix . && uv run ruff format .
uv run python -m unittest discover -s tests
```

## Rules that fail silently

Backend:
- Async SQLAlchemy, no `db` object. Models inherit `Base` from `stk/extensions.py`. Requests use `g.db_session`; CLI code and tasks use `ext.async_session_factory()`.
- Every handler is `async def`; every DB call is awaited. Import from `quart` and `quart_security`, never `flask*`.
- Every relationship uses `lazy="selectin"`. Never read a relationship on a row you just `add()`ed: load it with `await session.get(...)` or a query, or you get `MissingGreenlet`.
- `User.from_dict()`, `Activity.register()`, `Session.create_session()` and the auth signal handlers are async.
- Pagination is manual: `offset().limit()` plus `select(func.count())`. List endpoints return `orjson` via `Response(json.dumps(data), content_type="application/json")`.
- Mutations arrive as `{item: {...}}`: read `json_data.get("item", {})`.
- `Activity.register()` stores audit events and does not broadcast. `broadcast()` needs an explicit recipient and reaches only sockets on the same worker.
- SQLite migrations: DDL is not transactional; a new NOT NULL column needs `server_default` in migration and model; keep the constraint naming convention on `Base.metadata`.
- `stk verify` blocks drops, renames, retypes, and NOT NULL adds without a default in `upgrade()`. A rename is usually a mistaken drop + add from autogenerate; mark a deliberate one with `# destructive: <reason>`.
- Tests: subclass `TestingConfig` (`stk/settings.py`), never `Config`; `.env` loads at import. Pin any other env-driven switch a test depends on.
- Apps attach tables to core ones by foreign key (`user.id`); core models are fixed. App revisions depend on stk's head, so never merge heads by hand.
- An app overrides a template or static file by putting one at the same path; `stk/<name>` is the original. Override a block, do not copy the layout. Python is never overridden.

Frontend:
- Vue Options API (`data()`, `methods`, `mounted()`), never Composition API. Delimiters are `${}`. Every page uses `mixins: [layoutMixin]` and calls `registerStkComponents(app)` before mount.
- Server data JSON `<script>` tags go in `{% block js %}`, never `{% block content %}`: Vue strips scripts inside `#app`.
- Template expressions cannot see page globals: `app.config.globalProperties.name = value` before mount. The production build fails silently, so look at the rendered page.
- Vuetify 4 uses MD3 type classes (`text-title-large`, not `text-h6`); MD2 classes do nothing. Icons are Tabler (`ti ti-*`), never MDI.
- Logout is POST-only (`layoutMixin.logout()`).

Security:
- stk owns authentication in-process. Do not swap in a third-party auth service unless that is the task.
- All mutations require CSRF. A sessionless webhook opts out with `@csrf_exempt` from `stk.security` under the route decorator and must authenticate the caller itself (e.g. HMAC).
- Public password registration stays off by default. OAuth never auto-links emails and still enforces local MFA.
- Agent browser login (`STK_ENABLE_AGENT_LOGIN`) is development/testing only; startup fails elsewhere.
- Never commit secrets, databases, reviews, or machine paths: `stk verify` fails on them.

Product:
- Rename an app with `APP_NAME` / `APP_TAGLINE` / `APP_DESCRIPTION` and its own `templates/_brand.html` and favicon. Never edit names across templates.
- Before reporting UI work done, run `uv run stk smoke` and look at a screenshot with real rows. A 200 and green tests do not prove a page renders.
