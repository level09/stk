# Changelog

## Unreleased

- The docs move to https://docs.stkit.dev, matching the PyPI name. An app made by an earlier `stk init` points its `CLAUDE.md` and `.claude/skills/` at docs.stk.dev: replace it with docs.stkit.dev.
- stkit's PyPI page links to the docs, source and changelog.

## v17.1.0 (2026-10-25)

No migration required.

- `app_navigation()` returns the app's `app.navigation` entries alone, without stk's Dashboard, Account and Administration sections, for a layout that draws its own sidebar (Frontend, Navigation).
- The layout ships an import map, `{{ import_map() }}`, that maps every `.js` and `.mjs` file in the app's, extensions' and stk's static folders to its versioned URL, app first. A module imported by another module is fresh after a deploy too. A layout that does not extend `stk/layout.html` calls it in its `<head>` (Frontend).
- `build_alembic_config("myapp", url)` takes the app's import name with a URL, so a test can migrate a throwaway database before it builds its app. Passing the app still works (Models, Migrations).
- `stk db revision` imports the module of each column type Alembic writes by its path (pgvector's `HALFVEC` and `BIT`, an app's `UserDefinedType`), then sorts the revision's imports and formats it with the app's ruff config. Before, such revisions failed with a `NameError`.
- `stk db revision` warns about each column-level `CheckConstraint` in the columns it adds: Alembic autogenerate leaves them out. Declare checks in `__table_args__`, or add them to the revision by hand (Models, Migrations).
- Configuration documents app paths in `settings.py` (`Path(__file__).resolve().parent.parent`) in place of the removed `Config.PROJECT_ROOT`, and `app.root_path` and `app.instance_path` at runtime.

### Upgrade considerations

Nothing breaks. Apps can delete what they wrote around these gaps:

- A Jinja global that returns `app.navigation` (Sealbook's `rail_navigation` in `sealbook/shell/__init__.py`): call `app_navigation()` in the layout instead.
- An app import map (Sealbook's `import_map()` and `MODULE_DIRS` in `sealbook/assets.py`): stk's `import_map()` global has the same name, so a copied layout that calls `{{ import_map() }}` keeps working. stk's map also lists minified `.js` files; they are harmless there.
- Tests that import the module-level app only to call `build_alembic_config(app, url)`: pass `"myapp"` instead.
- Nothing in existing revisions: hand-written imports there stay correct. New revisions import their types themselves.

Paste-ready prompt for a coding agent:

```text
Upgrade this app to stkit 17.1.0 (bump the pin, `uv lock`). Then delete the workarounds 17.1.0 makes unnecessary: (1) any Jinja global returning app.navigation; call app_navigation() in the layout instead. (2) any app-built import map of versioned static modules; stk's import_map() global replaces it, so keep `{{ import_map() }}` in a copied layout and delete the app's function and its registration, plus test assertions that minified files are absent from the map. (3) in tests, `build_alembic_config(app, url, ...)` where the app was imported only for that: pass the app's import name, `build_alembic_config("<package>", url, ...)`, and drop the import. Leave existing migration revisions alone, including their hand-written imports and checks. Done when the tests, `uv run stk verify` and `uv run stk smoke` pass.
```

## v17.0.2 (2026-10-25)

No migration required.

- `stk verify` follows redirects from `/` and checks that the page it lands on answers 200, so an app whose `/` sends people to sign-in or to its own home passes. A redirect to a broken page still fails.
- Replacing stk's landing view is documented: `app.view_functions["public.index"] = home` in an extension's `init_app` (Architecture, Public).
- `STK_CLI_SECTIONS` groups an app's own commands in `stk --help`, after stk's sections, instead of listing them all under Other.

## v17.0.1 (2026-10-25)

No migration required.

- Every dependency is locked at its latest release and tested: SQLAlchemy 2.1, Quart 0.23, webauthn 3, uvicorn 0.54, cryptography 50.0.2, and the rest. `pip-audit` finds no known vulnerabilities.
- Requires quart-security 2.0.3, which declares the passkey usage choices the way wtforms 3.3 expects (tuple choices are removed in wtforms 3.4).
- The pre-commit ruff hook matches the locked ruff (0.17.2). Ruff now also formats the Python samples in the docs.

## v17.0.0 (2026-10-25)

stk becomes an installed, versioned package. An app is a separate, thin package that composes it and never edits a framework file, so upgrading stk is a version bump plus whatever its release note says.

### Breaking

- An app is no longer a fork of stk. `stk init <name>` writes an app package: `myapp/app.py` builds `Stk(__name__, config=Config, extensions=[...])`, settings are `class Config(stk.Config)` in `myapp/settings.py`, and the app depends on `stkit>=17,<18`: stk is published on PyPI as `stkit`, still imported as `stk` and run as `stk`. Commands find the app from `[tool.stk] app` in the nearest `pyproject.toml`, or from `STK_APP`.
- `create_app(Config)` is replaced by `Stk(import_name, config=..., extensions=[...])`. Each extension is a package with `init_app(app)`; its `models` module is imported before it is called. `run.py` is gone: uvicorn serves the `[tool.stk] app` value (`myapp.app:app`).
- Templates and static files resolve app first, then each extension's, then stk's. Core templates are reachable as `stk/<name>`. `layout.html` gains `title` and `navigation` blocks.
- The sidebar is data: `stk/static/js/navigation.js` is removed. Extensions add pages with `app.navigation.append({...})`; they appear under Dashboard in extension order.
- stk's migrations ship inside the package (`stk/migrations/`) as one squashed revision, `stk_0001`, with the branch label `stk`. An app keeps its own lineage in `myapp/migrations/`, and each app revision depends on stk's head. `stk db upgrade` runs `upgrade heads`. `alembic.ini` and the `alembic/` directory are gone. A database created by stk 16 is not upgraded.
- `stk new <module>` writes an extension into the app package and adds it to the app's `extensions` list; it no longer patches `stk/app.py` or `navigation.js`.
- `stk run` serves through uvicorn with a 3 second graceful shutdown, so Ctrl+C no longer hangs on open tabs. Its options are `--host`, `--port`, and `--reload/--no-reload`.
- Importing stk needs no environment: missing `SECRET_KEY` or `SECURITY_PASSWORD_SALT` fails when the app is built. `.env` is read from the working directory. `Config.APP_DIR` and `Config.PROJECT_ROOT` are removed; the default SQLite database is `instance/stk.db` beside the app package.
- `Dockerfile`, `docker-compose.yml`, `nginx/`, `postgres/`, and `.env-sample` move into the app template that `stk init` writes. Nginx and Caddy pass `/static/` to the app instead of reading `stk/static` from disk. `deploy.sh` requires `REPO`, your app's repository. `.gitattributes` and the merge-based upgrade guide are removed.
- `checks.py` moves to `stk/checks.py` and runs against the app. Its docs checks run only inside the stk repository.

### Also

- `stk db check` and `stk smoke` use a throwaway database of the configured dialect, so Postgres apps are checked on Postgres (the role needs CREATEDB). Autogenerate never offers to drop PostGIS's `spatial_ref_sys`. `stk.migrations.portable_tables()` returns the tables SQLite can build.
- Autogenerated revisions import what their column types need, and pass ruff without per-file exceptions.
- `stk doctor` reports the app it loaded and understands two lineages.
- `stk init` gives each app a `CLAUDE.md` (with `AGENTS.md` linked) carrying stk's rules and pointing at the docs, the stk skills, and a CI workflow running tests, `stk verify`, and `stk smoke`. `stk verify` in stk's repository fails when the template's rules drift from stk's.
- `stk new` uses English plurals for pages and APIs (`category` gives `/categories/`). Pass the singular name.
- stk moves from httpx to `httpx2`, with `authlib>=1.9.1` and `quart-security>=2.0.2` doing the same, so authlib no longer warns about its deprecated httpx fallback on every command.
- The unused `sidebar` and `layout_classes` blocks are gone from stk's templates and the scaffold.

### Upgrade considerations

There is nothing to upgrade from: 17.0.0 starts the new design. To move an app built on stk 16, start a fresh app with `stk init`, move each module into the app package with an `init_app`, move its settings into the app's `Config`, turn template and navigation edits into overrides and `app.navigation` entries, and replace its migration history with one fresh app revision. Paste-ready prompt for a coding agent:

```text
Move this app off its stk 16 fork onto stk 17. Run `uvx --from stkit stk init <name>` next to it. For each module the app added under stk/: move it to <name>/<module>/, give its __init__.py an init_app(app) that registers its blueprint and appends its sidebar entries to app.navigation, and add it to `extensions` in <name>/app.py. Move app settings into <name>/settings.py (class Config(stk.Config)). Replace edited stk templates with files at the same path in <name>/templates/ that extend "stk/<name>" and override blocks. Delete the old migrations, then run `uv run stk db upgrade` and `uv run stk db revision -m "initial"`. Done when `uv run stk verify` and `uv run stk smoke` pass and no file under stk is edited.
```

## v16.4.1 (2026-10-25)

No migration required.

- Apps built on stk upgrade by merging stk release tags: see Deployment, "Upgrading an app built on stk". `.gitattributes` keeps an app's README, CHANGELOG, lockfile, and brand files on merge once `git config merge.ours.driver true` is set. An app copied without stk's history records its starting commit once with `git merge -s ours --allow-unrelated-histories <commit>`.
- `stk smoke` skips every WebSocket route, not only `/ws`, and any path listed in the new `STK_SMOKE_SKIP` app config value.
- The Vue brace check in `stk verify` ignores `<script>` bodies, where JS template literals are valid.

## v16.4.0 (2026-10-25)

No migration required.

- New `stk-lessons` skill. When a failure the docs did not warn about costs an agent time, it logs one line in `.stk/lessons.md` and continues. On request, it triages the log: drops covered or one-off lessons, confirms the rest in code, and proposes each at the strongest home that holds (code default, `stk verify` check, `stk doctor` hint, docs line, skill step). Nothing applies without approval. Apps built on stk get framework lessons in generic terms to send upstream.

## v16.3.0 (2026-10-25)

No migration required.

- Static JS and CSS in the layouts load through `url_for('static', ...)`, which adds a content hash (`?v=...`). The app, `nginx/stk.conf`, and the Caddy config from `deploy.sh` cache versioned files forever and revalidate the rest. Servers set up by an earlier `deploy.sh` cached every static file for a year: re-run it or apply the new `handle_path /static/*` block to the Caddyfile.
- `alembic.ini` no longer names a database, so `uv run alembic` targets the app's database like `stk db` does.
- `Base` sets `eager_defaults`, so `server_default` and SQL `onupdate` columns are readable after a flush instead of raising `MissingGreenlet`.
- `TestingConfig` in `stk/settings.py` pins the database, sessions, mail, OAuth, rate limits, breach check, and agent login. Subclass it in tests instead of `Config` so `.env` never reaches them.
- `stk verify` fails on `{` inside a Vue `${ }` interpolation, which blanks the page.

## v16.2.1 (2026-10-23)

No migration required.

- `stk verify` fails on a migration whose `upgrade()` drops or renames a table or column, retypes a column, or adds a NOT NULL column without a `server_default`. Mark a deliberate step with a `# destructive: <reason>` comment inside `upgrade()`.
- `stk verify` fails when `CLAUDE.md` grows past 8KB or a skill past 4KB, so the agent index stays an index.

## v16.2.0 (2026-10-23)

No migration required.

- The docs in `docs/src/content/docs/` are the single source for humans and agents. `.stk/context/` and the `stk-dev` skill are removed; their content moved into the Frontend, Models, JSON APIs, Background Work, Build Loop, and Deployment pages. `AGENTS.md` is now an index of those pages plus the rules that fail silently. Apps that referenced `.stk/context/*.md` should point at the docs pages instead.
- `stk inspect commands` reports every command and option, as text, `--json`, or `--markdown`. The docs CLI reference is generated from it.
- `stk verify` fails when the CLI reference is stale, when `stk/settings.py` reads an environment variable the Configuration page does not list, when `AGENTS.md` misses a docs page, or when docs, skills, or the README point at a file that does not exist.
- New docs pages: Configuration, CLI Reference, Renaming Your App, and WebSockets in Background Work. The docs site uses the stk logo.

## v16.1.0 (2026-10-19)

No migration required. Existing databases keep their constraint names and show no drift.

- `APP_NAME`, `APP_TAGLINE` and `APP_DESCRIPTION` settings brand titles and auth pages. The logo lives in one partial, `stk/templates/_brand.html`. The placeholder Terms of Service and Privacy Policy line is removed from login and registration.
- `stk.security.csrf_exempt` lets a signed third-party webhook skip the CSRF token check. Host, API body and pagination checks still apply, and the view must authenticate the caller itself.
- `stk smoke` also visits every parameterless GET page, skipping auth flows, APIs and webhooks, and fails on uncaught page errors.
- Unhandled database errors return 500 and are logged instead of using the SQLAlchemy error code as the status.
- `stk db downgrade -1` accepts relative targets.
- `stk install` and `stk create` reject email addresses the login form would refuse.
- New constraints are named by a convention on `Base.metadata`, so SQLite batch migrations can add foreign keys.
- The navigation drawer starts closed on phones.
- `stk --version` reports the framework version when an app renames its package, and `setup.sh` runs without a terminal.

## v16.0.0 (2026-10-06)

Requires quart-security 2.0.1. Run `uv run stk db upgrade` and `uv run stk protect-mfa` before upgrading an existing deployment. Preserve the MFA encryption keys.

- Require CSRF tokens for application mutations and send them from Axios.
- Use single-use OAuth state, PKCE, signed Google ID tokens, and verified GitHub email. Disable automatic email linking and enforce local MFA and account lockout.
- Rotate Redis session IDs on authentication changes and keep tracking records aligned with revoked sessions.
- Use atomic SQL authentication limits across workers. Apply migration `20261006_0002` before starting the app.
- Bound WebSocket connections, queues, messages, and lifetime. Require same-origin connections and explicit broadcast recipients. Remove automatic audit broadcasts.
- Enforce admin password policy and bound API pagination. Use Argon2id for new passwords; existing hashes still verify.
- Encrypt enrolled and pending MFA seeds. `stk protect-mfa` encrypts dormant accounts and supports key rotation.
- Disable public password registration by default. Set `SECURITY_REGISTERABLE=True` only when required.
- Require unique database and Redis secrets plus TLS certificates in Docker Compose. Keep data services and the app port private.
- Update vulnerable runtime packages and add PostgreSQL and Redis security checks to CI.

See `SECURITY.md` for deployment requirements and review limits.

## v15.0.0 (2026-10-06)

Requires quart-security 2.0.0 and a database migration before startup.
Run `uv run stk db upgrade` to add the shared authentication-state table.
Existing login cookies are invalidated.

- Share database sessions between authentication and application routes.
- Revoke authentication state on logout, password resets, and single-session login.
- Preserve local HTTP cookie configuration and default to secure cookies.
- Pass application settings to password hashing in account commands.
- Add regression checks for startup, copied cookies, session revocation, and TOTP replay.

## v14.1.0 (2026-07-25)

### Added
- `stk doctor`: env, secrets, database, migration state, admin user, vendored
  assets, agent-login exposure, browser, and REPL, each problem with the command
  that fixes it. `--json` for tooling.
- `stk verify --watch`: re-runs only the checks a changed file can break (models
  touch migration drift, templates do not) and prints the remedy under a failure.
- Every verify check now carries its remedy, in the text output and in the JSON.
- `stk new <name>` generates and applies the migration, then prints the URL of the
  page it created. `--no-migrate` opts out.
- Docs: `build-loop.mdx` and `shell.mdx`, both example-first.

### Changed
- Alembic failures report one line plus a next step instead of a traceback.
- CI actions bumped off Node 20 (checkout v7, setup-uv v9, upload-artifact v7).
- `alembic.ini` sets `path_separator`, silencing the deprecation warning.

### Removed
- `stk migrate` and `stk migration-status`, pure aliases for `stk db upgrade` and
  `stk db current`.

## v14.0.0 (2026-07-25)

Bundles the unreleased 13.4.x work (hardened auth via quart-security 1.4.1) with a
new CLI, a frontend upgrade, and three gates that catch failures the old gate could
not see.

### Added
- `stk` command as the single entry point: grouped `--help`, app factory baked in
  (no `QUART_APP`), `python -m stk` and `uv run stk` both work. `quart <command>`
  keeps working.
- `stk shell`: async REPL with the app, a live `db` session, every model, query
  helpers, and top-level `await`. Uses ptpython (dev extra) for highlighting,
  fuzzy completion, and fish-style suggestions; falls back to the stdlib console.
  `stk shell -c "await count(User)"` for one-shot queries and scripts.
- `stk db check`: fails when models have drifted from migrations, measured by
  running migrations onto a throwaway database. Part of `stk verify`, so CI enforces it.
- `stk smoke` now visits `/`, measures WCAG contrast on every button, chip, and
  alert, and fails on text that is invisible against its background.
- `checks.py` asserts every route the report calls guarded actually rejects
  anonymous access.
- `vendor.sh` refreshes pinned frontend assets; versions recorded in
  `stk/static/VERSIONS.txt`.

### Changed
- **Vuetify 3.7.8 to 4.1.6.** Material Design 2 type classes are gone; 67 usages
  renamed to the MD3 names (`text-h5` to `text-headline-small`, and so on). Forks
  with custom templates must do the same rename. Mapping table in
  `.stk/context/frontend.md`.
- Vue 3.3.4 to 3.5.40, now the production build (was shipping the dev build).
  Axios to 1.18.1. Tabler Icons 3.45.0 self-hosted instead of an unpinned CDN.
- `stk/commands.py` (918 lines) split into `stk/cli/`: `agent`, `database`,
  `users`, `reports`, `smoke`, `base`.
- Route auth in `stk inspect routes` is read from the actual guard chain instead
  of guessed from path prefixes.
- `stk verify` prints the tail of a failing check instead of a bare cross.

### Fixed
- Seven security routes (`/change`, `/tf-setup`, `/wan-register`, and others) were
  reported as public while actually requiring auth.
- `GET /mf-recovery` returned 500 to anonymous users: the template used
  `mf_recovery_form` while quart-security passes `recovery_form`.
- Nav filtering mutated state inside a computed, which hung the dashboard under
  Vue 3.5's production reactivity (the dev build only warned).
- Buttons rendered as anchors took the link colour, so a primary button on a
  primary background was invisible. Vuetify 4 ships in CSS cascade layers, which
  let unlayered app CSS win.
- Smoke output redacted the agent-login token by list position, leaking it when a
  page was added.

### Removed
- 5.1MB of unused Material Design Icons (referenced nowhere).
- `register_shellcontext`, replaced by `stk shell`.
- Empty `stk/core/` and app packages left over from a killed branch.

## v11.3.0 (2025-12-02)

### Added
- Lite mode: Zero-config startup with `uv sync && flask run` — no Redis required
- Full mode: Optional Redis + Celery via `uv sync --extra full`
- SQLAlchemy-based sessions as default (Redis sessions optional)
- AI-assisted development with AGENTS.md for Claude Code and Cursor

### Changed
- Redis and Celery moved to optional dependencies
- SQLite database path now uses absolute path in `instance/stk.db`
- Updated documentation for lite/full mode workflow
- Simplified README with clearer positioning

## v11.2.0 (2025-04-24)

### Added
- Production-ready Docker configuration with multi-stage builds
- PostgreSQL service in Docker Compose setup
- Improved environment variable handling for Docker
- Support for user-specific Docker UID configuration
- Enhanced setup.sh script with Docker configuration option

### Changed
- Optimized Dockerfile with multi-stage build for smaller, more secure images
- Fixed Redis connectivity by using correct environment variables
- Improved nginx configuration with proper retry settings
- Enhanced tmpfs configuration for better performance
- Added proper health checks for all Docker services

## v11.1.0 (2025-03-30)

### Added
- Migrated from pip/venv to uv for package management
- Faster installation and dependency resolution
- Better Python environment isolation

### Changed
- Updated setup.sh script to use uv instead of venv
- Modified Dockerfile to use uv for package installation
- Updated documentation to reference uv

## v11.0 (2023-03-27)

### Added
- New activity model to track user actions like creating and editing users/roles
- Cursor Rules for improved code generation and assistance
- Comprehensive documentation for Cursor Rules approach

### Changed
- Improved user and roles tables design in both frontend and backend
- Transitioned from OpenAI integration to Cursor Rules for code generation
- Enhanced admin user creation with better console output

### Removed
- Removed flask-openai dependency and related code generation commands
- Removed OpenAI API key requirements

### Fixed
- Various UI and UX improvements
- Code cleanup and bug fixes 