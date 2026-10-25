---
title: "CLI Reference"
description: "Every stk command and option, generated from the code"
---

Generated from the live command tree by `uv run stk inspect commands --markdown`.
Do not edit it by hand: `stk verify` fails when this page and the code disagree.
Agents can read the same data as JSON with `uv run stk inspect commands --json`.

## Develop

### `stk init`

`stk init [OPTIONS] NAME`

Start a new app package NAME in ./NAME, depending on this stk version.

| Option | Description |
|---|---|
| `--source` | Install stk from this checkout or wheel instead of the stkit package. |

### `stk new`

`stk new [OPTIONS] NAME`

Scaffold a new extension module in the app, ending at a page you can open.

| Option | Description |
|---|---|
| `--migrate, --no-migrate` | Autogenerate and apply the migration for the new model. |
| `--port` | Port used in the URL. |

### `stk routes`

`stk routes [OPTIONS]`

Show all registered routes with endpoints and methods.

| Option | Description |
|---|---|
| `--sort, -s` | Method to sort routes by. "match" is the order that Quart will match routes when dispatching a request. |
| `--all-methods` | Show HEAD and OPTIONS methods. |

### `stk run`

`stk run [OPTIONS]`

Run a local development server (uvicorn, as in production).

| Option | Description |
|---|---|
| `--host` | The interface to bind to. |
| `-p, --port` | The port to bind to. |
| `--reload, --no-reload` | Restart on code changes (default: on when QUART_DEBUG is set). |

### `stk shell`

`stk shell [OPTIONS]`

Async REPL with the app, a live DB session, and all models loaded.

| Option | Description |
|---|---|
| `-c, --command` | Run code and exit. |

## Database

### `stk create-db`

`stk create-db [OPTIONS]`

Apply all database migrations (same as `stk db upgrade`).

### `stk db check`

`stk db check [OPTIONS]`

Fail if models have drifted away from the migrations.

### `stk db current`

`stk db current [OPTIONS]`

Show the current database revision.

### `stk db downgrade`

`stk db downgrade [OPTIONS] REVISION`

Downgrade the database to a target revision.

### `stk db history`

`stk db history [OPTIONS]`

Show migration history.

### `stk db revision`

`stk db revision [OPTIONS]`

Create a migration revision in the app's own lineage.

| Option | Description |
|---|---|
| `-m, --message` | Revision message |
| `--autogenerate, --empty` | Autogenerate from model metadata or create an empty revision |
| `--head` | Extend this head instead of the app's lineage (stk@head for core). |

### `stk db stamp`

`stk db stamp [OPTIONS] [REVISION]`

Stamp a database with a revision without running migrations.

### `stk db upgrade`

`stk db upgrade [OPTIONS] [REVISION]`

Upgrade the database: stk's migrations and the app's, to their heads.

## Verify

### `stk doctor`

`stk doctor [OPTIONS]`

Report the state of this checkout, and what to run for anything wrong.

| Option | Description |
|---|---|
| `--json` | Emit JSON. |

### `stk inspect commands`

`stk inspect commands [OPTIONS]`

Inspect every stk command and its options.

| Option | Description |
|---|---|
| `--json` | Emit JSON. |
| `--markdown` | Emit the docs CLI reference page. |

### `stk inspect context`

`stk inspect context [OPTIONS]`

Inspect routes and models as one agent-readable contract.

| Option | Description |
|---|---|
| `--json` | Emit JSON. |

### `stk inspect routes`

`stk inspect routes [OPTIONS]`

Inspect registered routes.

| Option | Description |
|---|---|
| `--json` | Emit JSON. |

### `stk report`

`stk report [OPTIONS]`

Generate a static project report.

| Option | Description |
|---|---|
| `-o, --output` | HTML output path. |
| `--json` | Emit JSON. |

### `stk smoke`

`stk smoke [OPTIONS]`

Run a real-browser smoke check against a temporary development app.

| Option | Description |
|---|---|
| `--json` | Emit JSON. |

### `stk verify`

`stk verify [OPTIONS]`

Run STK verification checks.

| Option | Description |
|---|---|
| `--json` | Emit JSON. |
| `-w, --watch` | Re-run affected checks on every file save. |

## Accounts

### `stk add-role`

`stk add-role [OPTIONS]`

Adds a role to the specified user.

| Option | Description |
|---|---|
| `-e, --email` |  |
| `-r, --role` |  |

### `stk browser-token create`

`stk browser-token create [OPTIONS]`

Create a signed test-only browser login URL.

| Option | Description |
|---|---|
| `--user` | Test user email. |
| `--ttl` | Token TTL in seconds. |
| `--next` | Local redirect path. |

### `stk cleanup-sessions`

`stk cleanup-sessions [OPTIONS]`

Deactivate expired sessions and delete old rows.

### `stk create`

`stk create [OPTIONS]`

Creates a user using an email.

| Option | Description |
|---|---|
| `-e, --email` |  |
| `-p, --password` |  |

### `stk install`

`stk install [OPTIONS]`

Install a default admin user and add an admin role to it.

| Option | Description |
|---|---|
| `-e, --email` | Admin email |
| `-p, --password` | Admin password |

### `stk protect-mfa`

`stk protect-mfa [OPTIONS]`

Encrypt legacy MFA seeds or rotate them to the current key.

### `stk reset`

`stk reset [OPTIONS]`

Reset a user password using email

| Option | Description |
|---|---|
| `-e, --email` |  |
| `-p, --password` |  |
