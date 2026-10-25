# CLAUDE.md

Guidance for coding agents working on __App__. `AGENTS.md` is a symlink to this file.

__App__ is built on stk, installed as the `stkit` package and imported as `stk`.
`__app__/app.py` composes it: `Stk(__name__, config=Config, extensions=[...])`, where each
extension is a package in `__app__/` with `init_app(app)`. Never edit stk's files: they
are replaced on every upgrade. Override a template or static file by putting one at the
same path in `__app__/templates/` or `__app__/static/`; `stk/<name>` is the original.

## Where truth lives

1. **The running app.** Ask it before reading files: `uv run stk inspect context --json` (routes with auth, models), `uv run stk inspect commands --json` (every command and option), `uv run stk doctor` (app state, each problem with its fix). `uv run stk new <module>` writes the canonical CRUD extension; copy its patterns.
2. **stk's docs** at https://docs.stk.dev, indexed for agents at https://docs.stk.dev/llms.txt. Read the page for your task before writing code.
3. **Skills** in `.claude/skills/` (mirrored at `.agents/skills/`): `stk-blueprint`, `stk-api`, `stk-migrate`, `stk-deploy`, and `stk-lessons` (when a gotcha the docs missed costs you time, log one line in `.stk/lessons.md`).

## Commands

```bash
uv run stk run                      # Dev server at localhost:5000 (--port 5001 on macOS)
uv run stk db upgrade               # stk's migrations, then the app's
uv run stk install                  # Create admin user
uv run stk doctor                   # What is wrong, and the command that fixes it
uv run stk new <module>             # Extension + migration, ends at a URL
uv run stk verify --watch           # Re-run affected checks on every save
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
