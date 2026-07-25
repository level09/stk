# Changelog

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
- Empty `stk/core/` and `stk/qarina/` packages left over from a killed branch.

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