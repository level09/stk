---
title: "The Build Loop"
description: "Scaffold, edit, and know instantly whether you broke something"
sidebar:
  label: "Build Loop"
---

Every stk command lives under `stk`. Run `stk --help` to see them grouped by purpose.

```bash
uv run stk --help
```

Prefer bare `stk`? Activate the venv once per shell:

```bash
source .venv/bin/activate
stk run
```

## 1. Is everything ready?

```bash
uv run stk doctor
```

```
✓ env file       .env
✓ app            myapp.app:app
✓ secrets        SECRET_KEY and password salt look random
✓ database       sqlite stk.db (124 KiB)
! migrations     database is behind: stk_0002 not applied
    → uv run stk db upgrade
✓ admin user     1 admin(s)
✓ assets         vue 3.5.40 vuetify 4.1.6
✓ agent login    disabled
✓ browser        chromium ready for stk smoke
✓ shell          ptpython: highlighting and completion

Usable, with the warnings above.
```

Every line that is not `✓` tells you the command that fixes it. A `!` is a warning, a
`✗` is a failure, and the exit code is `1` only on a failure, so it works in scripts.
`--json` for tooling.

## 2. Scaffold a feature

```bash
uv run stk new invoice
```

`NAME` is a lowercase snake_case identifier. This writes an extension package into your
app (`myapp/invoice/`: model, views, template, and an `init_app` that registers the
blueprint and its sidebar entry), adds it to `extensions` in `myapp/app.py`, generates
the migration for the new model in the app's lineage, applies it, and then tells you
where to look. It never touches stk's files:

```
Open: http://localhost:5000/invoices/  (start it with: stk run)
```

Pass `--no-migrate` if you would rather write the migration yourself, and `--port` if
your dev server is not on 5000.

## 3. Keep the gate running while you edit

```bash
uv run stk verify --watch
```

It checks everything once, then polls for saved files and re-runs only what the change
can break. A `.py` edit re-runs ruff, the sanity checks, and migration drift; a template,
JS, or CSS edit re-runs only the sanity checks.

```
changed: myapp/invoice/models.py
✗ migration-drift
    add_column: invoice due_date
    → uv run stk db revision -m "describe change" && uv run stk db upgrade
✓ ruff
✓ checks
```

Leave it in a split pane. You find out the moment you break something, not ten
minutes later, and the fix is on screen.

## 4. Prove it in a real browser

```bash
uv run stk smoke
```

Boots a throwaway app on a free port against a temporary database, drives Chromium
through the home page, login, dashboard, and admin users page, then visits every other
GET page that takes no URL arguments. It fails on any of: an HTTP status of 400 or
above, a console or uncaught error, a failed request, or button, chip, and alert text
below 3:1 contrast with its background. That last one catches the class of bug no
console error ever reports. The dashboard screenshot lands in
`.stk/smoke/dashboard.png`; `--json` emits the per-page report.

Smoke needs Playwright's Chromium. `stk doctor` tells you if it is missing.

## 5. Ship

```bash
uv run stk verify && uv run stk smoke
uv run stk report          # docs/stk-report.html: routes, auth, gate results
```

`stk verify` runs ruff, the sanity checks in `stk/checks.py` against your app, and migration drift, and exits `1` if any fail.
CI runs both `stk verify --json` and `stk smoke --json` (after the unit tests), so the
pair above is the same gate locally. `stk report --json` prints the routes and verify
results instead of writing HTML, and `-o` picks another output path.

## Which checks a change needs

`stk verify` and `stk smoke` are the gate for everything. Some changes need one more look:

| You changed | Also run |
|---|---|
| Templates, JS, or CSS | `uv run stk smoke`, then look at the screenshot with real rows |
| Models | `uv run stk db check` and `uv run stk db current` |
| Routes or auth | `uv run stk inspect routes --json`, then `uv run stk report` |
| Anything with logic | `uv run python -m unittest discover -s tests` |

A 200 response and green tests do not prove that columns, labels, or buttons render. Look at the page.

Test configs subclass `TestingConfig` from `stk/settings.py`, not `Config`: `.env` loads at import, and `TestingConfig` pins the database, sessions, mail, OAuth, rate limits, and agent login so a developer's settings never reach a test. Pin anything else your test depends on. Never name a test method `run`: on `IsolatedAsyncioTestCase` it replaces `TestCase.run` and the class silently runs nothing. Run a new test once by its full name and see it reported.

To stop a dev server, stop the process on its port (`lsof -tiTCP:5000 -sTCP:LISTEN | xargs kill`), not a process name pattern that can match another checkout's server.

## Signing in as a test user

Agents and scripts that drive a browser can skip the login form with a short-lived token:

```bash
STK_ENV=development STK_ENABLE_AGENT_LOGIN=1 uv run stk browser-token create --user admin@example.com --ttl 60 --next /dashboard/
```

Open the printed `/_test/login?token=...` path: it creates a normal session and redirects to `--next`. The route exists only when all of these hold, and startup fails if it is enabled anywhere else:

1. `STK_ENABLE_AGENT_LOGIN=1`
2. `STK_ENV=development`, or the app is in testing mode
3. the token is signed and younger than `STK_AGENT_LOGIN_MAX_TTL_SECONDS`
4. the user's email ends in `@example.com`

`stk smoke` uses the same route with a throwaway `smoke@example.com` admin.

## The whole loop

```bash
uv run stk doctor              # am I ready?
uv run stk new invoice         # scaffold to a clickable URL
uv run stk verify --watch      # instant feedback while editing
uv run stk smoke               # real browser before shipping
```
