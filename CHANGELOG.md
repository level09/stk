# Changelog

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