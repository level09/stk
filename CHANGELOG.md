# Changelog

## v17.9.4 (2026-11-04)

No migration required.

- `stk smoke` names the cause when low-contrast text sits on nothing painted (the browser canvas shows through, usually in the dark theme of an app that replaced `app.css`): "sits on no page background ... give body a background", instead of a ratio against an assumed white.
- `config.js` puts `dark-mode` on `<html>` and `<body>` before Vue mounts, from the saved theme, so app CSS that switches on it never flashes light.

## v17.9.3 (2026-11-04)

No migration required.

- The app bar title takes its natural width and shrinks only when the bar is full (`flex: 0 1 auto`). 17.9.1's `flex: none` kept a long brand whole by pushing the user menu off a phone screen; now the brand truncates first and every button stays reachable.

## v17.9.2 (2026-11-04)

No migration required.

- Pages start in the saved theme. `config.js` picks it the way the theme switcher did (saved choice, then `__settings__.dark`, then the system), so Vuetify is created dark instead of rendering light and animating to dark after mount. That animation made `stk smoke`'s dark pass measure text mid-transition and report false 1:1 contrast; users saw it as a flash on every page.
- `auth_layout.html` and `login-layout.html` have the `csrf-token` meta and set axios's `X-CSRFToken` header, like `layout.html`, so a public page that POSTs needs no workaround.
- `stk doctor` treats `static/css/app.css` as a slot: it is stk's look, which an app with its own theme replaces.

## v17.9.1 (2026-11-04)

No migration required. Apps with their own `_head.html` that want stk's fonts add the Google Fonts link to it.

- stk's Google Fonts link moved from `layout.html` into `_head.html`, beside the favicon: an app with its own type no longer loads three unused families, and the sign-in pages now load stk's fonts too.
- The app bar's title no longer shrinks, so the brand is not clipped on a phone, with or without the menu button.

## v17.9.0 (2026-11-04)

No migration required. Apps with their own `_head.html` must add their favicon link to it.

- `configureApp(config)` and `registerAppComponents(app)`: functions an app defines in a script from `_head.html` to change the Vuetify config and add global components, instead of copying `config.js` or `components/index.js`. A copied `index.js` silently dropped 17.8.0's `dark-mode` mirror in one app.
- `stk doctor` warns about every app template or static file that replaces a stk file whole, since a copy stops receiving stk's fixes. Templates that extend `stk/<name>`, `_brand.html`, `_head.html`, `index.html`, `dashboard.html` and images pass.
- `stk smoke` runs the signed-in pages again in the dark theme (`dashboard dark`, `dashboard-dark.png`) with the same checks except copy, so a page that breaks only at night fails.
- The meta description is `APP_DESCRIPTION` (none when empty), not stk's tagline, and the favicon link moved into `_head.html`, so an app's own `_head.html` owns its favicon in any format.

## v17.8.0 (2026-11-04)

No migration required.

- `layout.html` has the blocks `app_bar_actions`, `user_menu` and `sidebar`, so an app gets a top-bar-only shell by emptying `sidebar` and adding its links to `user_menu`, instead of overriding the whole layout. The app bar's menu button only appears when the sidebar renders.
- The sign-in and sign-up photo loads through `url_for`, so an app's `static/img/auth-bg.webp` replaces it with a versioned URL that busts the browser's cached copy of stk's.

## v17.7.0 (2026-11-04)

No migration required.

- `_head.html`: every layout, including the sign-in pages', includes it in `<head>` outside any block, so an app's fonts, tokens and scripts stay on admin pages that empty the `css` block and on sign-in pages that replace every block. Put yours at `myapp/templates/_head.html`; stk's is empty.
- The root component mirrors the Vuetify theme as `dark-mode` on `<html>` and `<body>` on every page that calls `registerStkComponents`, not only on `<body>` where the theme switcher is mounted. Apps that patched this in themselves (an `html.night` mixin) can delete the patch and select on `.dark-mode`.

## v17.6.1 (2026-11-03)

No migration required.

- Navigation badges take their text colour from the theme (`on-primary`, `on-error`, `on-success`, `on-warning`) instead of white, which fell to about 2.6:1 on a light primary.
- `broadcast` with a non-numeric `user_id` raises a `ValueError` that names the argument and the value, instead of `int()`'s bare message.

## v17.6.0 (2026-11-03)

No migration required.

- `stk smoke` saves a full-page screenshot of every page it visits in `.stk/smoke/`, named after the page (`/monitor/runs` as `monitor-runs.png`), not only the dashboard. With `seed.py` that means a look at every list with rows. `--json` gives each page's `screenshot` path; each run clears the previous run's screenshots.

## v17.5.0 (2026-11-03)

No migration required.

- `seed.py`: an app's `async def run(session)` that adds sample rows. `stk smoke` runs it on its temporary database, so pages render rows instead of empty states and a template that breaks only on a row fails smoke, locally and in CI. `--json` reports `seeded`. `stk db seed` adds the same rows to the dev database, and `stk new` writes `seed.py` for its model when the app has none.
- `stk install` no longer crashes when the database has more than one admin.
- `stk smoke` keeps Redis off in its server: it removed the setting, and the server's own `.env` load put it back.

## v17.4.2 (2026-11-02)

No migration required.

- An app model named `User`, `Role`, `WebAuthn` or another core name no longer breaks stk's own mappers: core refers to its models by class, never by string.
- New core models carry an `Stk` prefix, enforced by a test in stk, so a release can no longer add a generic name the way 17.4.0 added `Message`.
- Models: if your app reuses a core class name (`Activity`, `File`, `Job`, `McpToken`, `Notification`, `OAuth`, `RateLimitWindow`, `Session`, `WebAuthn`), reference yours by class, not by string.

## v17.4.1 (2026-11-02)

No migration required.

- The model behind `stk_message` is now `StkMessage`. In 17.4.0 it was `Message`, which broke every mapper in an app that has its own `Message` model referenced by string, as in `relationship("Message")` ("Multiple classes found for path"). Apps that worked around it by passing the class can keep doing so.

## v17.4.0 (2026-11-02)

Run `uv run stk db upgrade`: migration `stk_0008` adds the `stk_message` table.

- `broadcast` reaches a user's sockets from any process: another uvicorn worker, a durable job in `stk worker`, or `stk shell`. Messages go through `stk_message`, which each server process polls while it holds sockets, so delivery lags up to a quarter second. Every call is now a database write, so throttle rapid progress updates. `user_id` must be a numeric user id.
- `broadcast(..., session=)` and `notify(..., session=)` join the caller's transaction: sent at commit, dropped on rollback.
- `notify` from a durable job now reaches open pages instead of waiting for the next page load.
- `stk run` on a port that is already taken exits with the pid holding it, instead of uvicorn's easy-to-miss log line while the old server keeps serving.
- The dev extra requires Playwright 1.64. Older versions never reach network idle on a page that opens an EventSource, so `stk smoke` timed out there. Apps on an older lock: `uv lock --upgrade-package playwright`.
- `stk --version`, the MCP server info and `stk init` read the installed package version. 17.3.2 still reported 17.3.1, so apps made with it require `stkit>=17.3.1`.

## v17.3.2 (2026-11-01)

No migration required. Requires quart-security 2.2.0, which normalizes emails more fully: an account stored with a decomposed Unicode or punycode email must be rewritten with `quart_security.normalize_email` to sign in. ASCII addresses are unaffected.

- When an admin changes a user's email, the user is signed out everywhere and their MCP tokens are revoked, so reset and confirmation links sent to the old address stop working. Retyping the same address in other case is no change (Authentication).
- Pages behind `auth_required`, which includes every admin page, now come back after login. Before, the user always landed on the dashboard.
- One mailbox is one account: `josé@` composed and decomposed, or `münchen.de` and its punycode form, no longer make separate users. Passwords match whichever Unicode form they are typed in.
- Passkey sign-in refuses locked and unconfirmed accounts, like password login.
- `STK_PUBLIC_URL` with a trailing slash no longer closes every WebSocket with 4003.
- A static file is cached as immutable only under the version this instance would link to. During a rolling deploy an old instance could pin old bytes under a new URL for a year. An app test that requests a made-up `?v=` and expects `immutable` must build the URL with `url_for('static', ...)` instead.

## v17.3.1 (2026-10-31)

No migration required.

- Versioned static responses were marked public and immutable for a year even when they were a 404 or carried a session cookie change, such as clearing a stale login. A shared cache could then replay them to other visitors. Only a 200 with no cookie change is cached publicly now; a response that changes the session is `private, no-store`.
- `stk smoke`'s raw-score rule could take tens of seconds on a page with a long run of blanks after the word "score", from two adjacent optional-blank patterns backtracking. It is linear now (Build Loop).

## v17.3.0 (2026-10-31)

Run `uv run stk db upgrade`: `stk_0007` marks every existing account confirmed. Requires quart-security 2.1.0.

- Password reset by email at `/reset`, on by default once `MAIL_SERVER` and `STK_PUBLIC_URL` are both set (`SECURITY_RECOVERABLE` overrides). Links work once, for one hour, and die if the email or password changes. A reset signs out every session, revokes MCP tokens and clears a lockout (Authentication).
- Public sign-up now requires email confirmation (`SECURITY_CONFIRMABLE`, default on). An unconfirmed account fails login exactly like a wrong password, which closes the last way to find accounts through sign-up. With `SECURITY_REGISTERABLE=true`, startup fails without `MAIL_SERVER`; set `SECURITY_CONFIRMABLE=false` to keep unconfirmed sign-up (Authentication).
- Users created by code, the CLI, admins or OAuth start confirmed: `User()` sets `confirmed_at` unless given one.
- A locked account now fails login with the same message as a wrong password.
- Auth mail links come from `STK_PUBLIC_URL` (as `SECURITY_PUBLIC_URL`), never the Host header. The 17.2.7 sign-up notice now comes from quart-security.
- The reset, resend and confirm pages use the current auth layout.

## v17.2.7 (2026-10-31)

No migration required. Requires quart-security 2.0.6.

- Registration no longer reveals which emails have an account: an existing email gets the same answer as a new one and nothing is created. With `MAIL_SERVER` set, the owner is emailed in the background that someone tried; its link comes from `STK_PUBLIC_URL`, never the request's Host header (Authentication).
- After login, users land back on the page that sent them to `/login`, including through 2FA and passkeys (Authentication).
- `stk.files` refuses to start when `STK_UPLOAD_MAX_BYTES` does not fit under Quart's `MAX_CONTENT_LENGTH`. Before, any limit above about 16 MiB was silently capped with a generic 413 (Configuration).
- `stk doctor` warns when `STK_PUBLIC_URL` is unset outside development, since any Host header is then accepted.

## v17.2.6 (2026-10-31)

No migration required.

- `stk smoke`'s `hex-id` rule no longer flags mixed-case names such as `Ed25519`. Ids are printed in one case, so `1fbaac41` and `1FBAAC41` still fail (Build Loop).

## v17.2.5 (2026-10-31)

No migration required.

- `stk smoke` crashed on any page with three or more like SVG shapes side by side, such as a chart's paths or an icon's circles: the repeated-row rule read `innerText`, which SVG elements lack. The rule now looks at HTML elements only. A page smoke cannot read now fails that page with the reason, instead of stopping the whole run (Build Loop).

## v17.2.4 (2026-10-31)

No migration required.

- Notifications are opt-in, like uploads and MCP: add `stk.notification` to the app's extensions for the `/api/notifications` routes and the layout's bell. From 17.2.0 to 17.2.3 stk registered those routes in every app, and because the first matching route answers, an app's own `/api/notifications` was silently never reached. `notify()` still stores rows without it (Background Work).
- `stk verify` fails when two endpoints register the same path and method, naming both, so a shadowed route can no longer ship silently.
- Apps made by `stk init`, and the example app, list `stk.notification`.

### Upgrade considerations

- An app that uses stk's bell adds `import stk.notification` and puts `stk.notification` in its `extensions` list, or the bell disappears and `/api/notifications` returns 404.

## v17.2.3 (2026-10-31)

Run `uv run stk db upgrade`.

- MCP is opt-in, like file uploads: add `stk.mcp` to the app's extensions. Without it stk registers no `mcp` blueprint, no `/mcp`, no `/tokens/` page and no Agent Tokens menu entry, so an app can serve its own MCP endpoint. From 17.2.0 to 17.2.2 stk claimed all of them in every app (JSON APIs).
- stk's MCP token table is `stk_mcp_token`, like every other core table. 17.2.0 to 17.2.2 created `mcp_token`, which failed to migrate in an app that already had a table by that name. Revision `stk_0006` moves stk's own tokens across; an app's own `mcp_token` is recognised by its columns and left alone.
- `stk.utils.netguard` adds `stream`, which yields the response with its body unread for large downloads and can cap decoded bytes with `max_bytes` or return a redirect with `follow_redirects=False`, and a public `pin(url)` that vets a URL without fetching it, for a client such as a headless browser. `fetch` is built on `stream`. Cookies are never carried across redirect hops (JSON APIs).

### Upgrade considerations

- An app that uses stk's MCP tools adds `stk.mcp` to its extensions, or `/mcp` and `/tokens/` return 404. Existing tokens keep working after `stk db upgrade`.

## v17.2.2 (2026-10-31)

No migration required.

- `stk add-role` and `stk cleanup-sessions` crashed with `TypeError: 'NoneType' object is not callable` because they used the database before the app was built. Every command that runs async work now builds the app first. Run `cleanup-sessions` from cron again if you had stopped it.
- `stk worker` stops on SIGTERM or Ctrl-C at a safe point: it cancels only the running job, hands it back, and exits without a traceback.
- The home page describes stk as running on Quart, not Flask.
- Requires quart-security 2.0.5: login takes the same time whether or not an email has an account, and passkey registration refuses a credential ID another user already holds (Authentication).

## v17.2.1 (2026-10-31)

No migration required.

- Emails are stored trimmed and lowercased, and the CLI, agent login and OAuth look users up regardless of case, matching what the login form does. Before, a user created as `Ada@Example.com` from the admin page or `stk create` could not sign in, because login lowercases what it is given (Authentication).
- Requires quart-security 2.0.4, which matches login emails regardless of case and drops the unused `remember` login field and `SECURITY_FRESHNESS_GRACE_PERIOD` setting. stk's own `SECURITY_FRESHNESS_GRACE_PERIOD` is removed with it.

### Upgrade considerations

- Existing rows keep their stored case and still sign in. Two rows whose emails differ only by case make login for that address fail: merge or rename one. To find them: `uv run stk shell -c "await sql('select lower(email), count(*) from \"user\" group by 1 having count(*) > 1')"`.
- A custom login template that renders `form.remember` must drop it.

## v17.2.0 (2026-10-31)

Run `uv run stk db upgrade`: four new core tables (`stk_job`, `stk_file`, `stk_notification`, `mcp_token`).

- Durable jobs that survive a restart. Register an async function with `@job`, queue it with `await enqueue(name, **payload)`, and run `uv run stk worker`. A job's writes commit together with its `done` mark; a failure rolls back, keeps the traceback, and retries after 30 and 60 seconds before staying `failed`. Each claim holds a lease of the worker's `--timeout` plus a minute, so a crashed worker's job is requeued and a worker that lost its claim discards its writes. Admins see jobs at `/jobs/` (Background Work).
- In-app notifications. `await notify(user_id, title, link=..., kind=..., body=...)` stores one and pushes it over the user's open sockets; the layout's bell shows the unread count and marks items read. `link` must be a same-origin path. JSON endpoints under `/api/notifications` list, count and mark the current user's notifications (Background Work).
- File uploads, opt-in: add `stk.files` to the app's extensions. `POST /files/` stores bytes once by their sha256 under `STK_UPLOAD_DIR`, detects the type from the bytes, enforces `STK_UPLOAD_MAX_BYTES` and `STK_UPLOAD_TYPES`, and makes WebP thumbnails for images. Downloads go to the uploader or an admin unless the app sets `app.file_access` (JSON APIs).
- Agent tools over MCP. Register a function with `@tool(name, description, schema, role=...)` from `stk.mcp`, and agents call it at `/mcp` with a personal token created at `/tokens/`. Tokens are stored as a hash, expire after 90 days, are limited to the user's current roles on every call, and stop working when the user's password changes. Every call is logged as an activity without its arguments. No OAuth sign-in yet: clients send the token as a header (JSON APIs).
- `fetch` from `stk.utils.netguard` fetches a URL a user supplied without reaching internal addresses: it refuses private, loopback, link-local, metadata and other non-public addresses, pins the checked IP against DNS rebinding, re-checks every redirect, and drops `Authorization` and `Cookie` when a redirect changes origin (JSON APIs).
- `stk smoke` fails on screens that work but read badly: uuids, raw hex ids, snake_case, raw scores, "1 items", `undefined`/`null`/`NaN`/`[object Object]`, and rows repeated three or more times. Allow deliberate text with `STK_SMOKE_COPY_ALLOW` (Build Loop).
- `stk verify`, `stk doctor` and `stk smoke` keep every failure's reason; `stk verify --json` lists each sanity check with its status and detail (Build Loop).
- New dependency: `jsonschema`, which validates MCP tool arguments.

### Upgrade considerations

- The layout's bell is now backed by stk. `layoutMixin` no longer has `notifications`, `handleNotificationClick`, `markNotificationRead`, `markAllNotificationsRead` or `removeNotification`. A page that used them, or that broadcasts `{"type": "notification", ...}` itself, calls `notify()` instead. Layouts that do not extend `stk/layout.html` are unaffected.
- stk now has a built-in `worker` command. An app command named `worker` is shadowed by it; rename the app's command.
- `enqueue()` and `notify()` commit on their own session, so a request that later rolls back still keeps the job or notification. Call them after your own commit.

## v17.1.1 (2026-10-28)

No migration required.

- The docs move to https://docs.stkit.dev, matching the PyPI name. An app made by an earlier `stk init` points its `CLAUDE.md` and `.claude/skills/` at docs.stk.dev: replace it with docs.stkit.dev.
- stkit's PyPI page links to the docs, source and changelog.
- Vendored Vue 3.5.44, Vuetify 4.3.1, axios 1.21.0 (fixes GHSA-m8m8-qj5v-23w3, GHSA-x97p-jq2g-jp4f and ten other axios advisories) and Tabler icons 3.50.0. Tabler now ships its font as unicode-range subsets in `icons/fonts/`, so the browser loads only the groups a page uses; `icons/fonts/tabler-icons.woff2` is gone. An app that preloads that file links `icons/fonts/tabler-icons.core.woff2` instead (Frontend).
- stkit's dependency minimums no longer allow versions with known vulnerabilities: cryptography 50.0.0, aiosmtplib 5.1.2, orjson 3.11.6, python-dotenv 1.2.2. An app that pins an older one gets a resolver conflict; raise its pin.
- CI audits the locked dependencies for known vulnerabilities with `uv audit`.

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