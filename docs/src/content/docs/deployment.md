---
title: "Deployment"
description: "Deploy your stk application to production"
sidebar:
  label: "Deployment"
---

## Overview

There are three ways to deploy: the one-command VPS script, Docker Compose, or a manual setup. All of them must meet the production requirements below. The full contract lives in [SECURITY.md](https://github.com/level09/stk/blob/master/SECURITY.md).

## Production requirements

Set these in `.env` before the app serves real traffic. `./setup.sh` writes development values (`QUART_DEBUG=1`, `STK_ENV=development`, `SESSION_COOKIE_SECURE=False`), so change them.

```bash
STK_ENV=production
QUART_DEBUG=0
SESSION_COOKIE_SECURE=True
SECRET_KEY=...                  # unique, generated
SECURITY_PASSWORD_SALT=...      # unique, generated
STK_PUBLIC_URL=https://app.example.com
SECURITY_WAN_RP_ID=app.example.com
SECURITY_WAN_EXPECTED_ORIGIN=https://app.example.com
```

`STK_PUBLIC_URL` restricts accepted request hosts and fixes OAuth callback URLs. The WebAuthn values must match the public host and origin or passkeys fail. Keep `SECURITY_REGISTERABLE=False` unless the app needs public sign-up.

`SECRET_KEY` also derives the default key for encrypted TOTP seeds, so keep it stable, or move to `SECURITY_TOTP_ENCRYPTION_KEYS` as described in [Authentication](/authentication). Back up the MFA keys separately from the database.

Trust proxy headers only from your own proxy. Rate limits key on the client IP, so a misconfigured proxy either collapses all users onto one IP or lets clients spoof theirs.

## Upgrading an existing deployment

Take a protected backup, then before starting the new version:

```bash
uv sync --frozen --extra full    # drop --extra full if you do not use PostgreSQL or Redis
uv run stk db upgrade
uv run stk protect-mfa
```

`protect-mfa` encrypts legacy TOTP seeds and rotates existing ones to the current key in one transaction. Version 16 needs the `rate_limit_window` table and version 15 the `quart_security_state` table; `db upgrade` creates both.

## Upgrading an app built on stk

An app is a git fork of stk and takes framework releases with an ordinary merge: your changes and stk's combine, and only real overlaps conflict. Once per clone:

```bash
git remote add stk https://github.com/level09/stk.git
git config merge.ours.driver true    # honours merge=ours in .gitattributes
```

For each release, on a branch:

```bash
git fetch stk --tags
git merge <tag>
uv lock && uv sync && uv run stk db upgrade
uv run stk verify && uv run stk smoke
```

`.gitattributes` keeps the app's README, CHANGELOG, lockfile, and brand files. Resolve other conflicts by keeping both the app's behavior and the framework's fix, then read stk's release notes (`git show <tag>:CHANGELOG.md`) for steps a merge cannot do, such as server config. Upgrades conflict less when app code lives in its own files instead of edits to framework ones.

An app copied without stk's history first records the stk commit the copy came from:

```bash
git merge -s ours --allow-unrelated-histories <commit>
```

Choose it with care: a merge skips every change up to that commit, so a later guess silently drops fixes. Compare candidates with `git diff --shortstat <commit> HEAD -- stk` and take the closest; between near-ties, prefer the older one, which costs a conflict instead of a lost fix.

## VPS deploy script

On a fresh Ubuntu 22.04 or 24.04 server:

```bash
wget -qO /tmp/deploy.sh https://raw.githubusercontent.com/level09/stk/master/deploy.sh && sudo DOMAIN=example.com bash /tmp/deploy.sh
```

`deploy.sh` installs Caddy with automatic TLS, uv-managed Python 3.13, a dedicated app user, UFW, fail2ban, and key-only SSH. It generates a production `.env` with fresh secrets and the public URL and WebAuthn values, applies migrations, creates an admin user, and runs uvicorn as a systemd service named after the domain. SQLite is the default; `DB=postgres` adds PostgreSQL, Redis, and the `full` extra. Admin credentials are saved to `/home/<user>/.credentials`.

| Variable | Default | Description |
|----------|---------|-------------|
| `DOMAIN` | (required) | Domain name, or server IP with `SKIP_SSL=true` |
| `REPO` | `level09/stk` | GitHub repository to deploy |
| `BRANCH` | `master` | Branch to deploy |
| `DB` | `sqlite` | `sqlite` or `postgres` |
| `ADMIN_EMAIL` | `admin@$DOMAIN` | Admin login email |
| `ADMIN_PASSWORD` | (generated) | Admin password |
| `SKIP_SSL` | `false` | `true` serves plain HTTP, for IP-only testing |
| `PYTHON_PORT` | `5000` | Internal uvicorn port |

`deploy.sh` is install-only. It deletes and re-clones the app directory, and with SQLite the database lives inside it at `instance/stk.db`, so running it again on a live server destroys production data. It also clones over plain HTTPS, so a private repository fails at the clone step: make it public, or clone it yourself with a read-only deploy key first.

Update a deployed app as the app user, in the app directory:

```bash
git pull && uv sync --frozen --no-dev && uv run stk db upgrade && sudo systemctl restart <domain>.service
```

Add `--extra full` to the sync on a PostgreSQL install, and run `protect-mfa` as above. The app user's sudoers entry allows managing only its own service.

Check a deploy with `curl -sI https://<domain>/` (expect 200 or a redirect to login) and `systemctl is-active <domain>.service`, then sign in with the saved credentials, create a record, restart the service, and confirm the record is still there.

## Docker Compose

```bash
docker compose up --build
```

The stack runs Redis, PostgreSQL 15, the app, and Nginx. The app container runs `stk db upgrade` before starting uvicorn, and Compose sets `STK_ENV=production`, `QUART_DEBUG=0`, `SESSION_COOKIE_SECURE=True`, the database and Redis URLs, and the public URL and WebAuthn values from `STK_HOST`. Compose refuses to start until `.env` provides:

```bash
DB_ADMIN_PASSWORD=...     # PostgreSQL superuser
DB_PASSWORD=...           # app database role
REDIS_PASSWORD=...
STK_HOST=app.example.com
TLS_CERTIFICATE=/absolute/path/fullchain.pem
TLS_PRIVATE_KEY=/absolute/path/key.pem
```

Passwords must be unique and URL-safe because they are embedded in connection URLs. `STK_HOST` is the bare DNS name; Compose derives `https://` URLs from it. The certificate paths must be absolute, valid for that host, and readable by the Nginx container user (`DOCKER_UID`, default 1000). Renew certificates and reload Nginx before they expire.

Only Nginx is published: port 80 redirects to HTTPS on 443. A new PostgreSQL volume gets a separate non-superuser `stk` role for the app. Initialization scripts do not run on an existing volume, so review that role's privileges yourself.

## Manual setup

You need Python 3.11+, uv, and a TLS-terminating reverse proxy. PostgreSQL and Redis are optional.

```bash
git clone https://github.com/level09/stk.git
cd stk
./setup.sh                    # deps and .env with generated secrets
uv sync --frozen --extra full # only for PostgreSQL or Redis
# edit .env with the production requirements above
uv run stk create-db
uv run stk install
```

SQLite works with no configuration and lives in `instance/stk.db`. For PostgreSQL, set `SQLALCHEMY_DATABASE_URI=postgresql+asyncpg://user:password@localhost/dbname`; the `postgresql://` scheme will not work. For Redis sessions, set `REDIS_URL`.

Run uvicorn under systemd, bound to localhost and trusting forwarded headers only from the local proxy:

```ini
[Unit]
Description=stk
After=network.target

[Service]
User=your_user
WorkingDirectory=/path/to/stk
EnvironmentFile=/path/to/stk/.env
ExecStart=/path/to/stk/.venv/bin/uvicorn run:app --host 127.0.0.1 --port 5000 --ws-max-size 65536 --ws-max-queue 16 --proxy-headers --forwarded-allow-ips=127.0.0.1
Restart=always

[Install]
WantedBy=multi-user.target
```

The proxy must pass `Host` and `X-Forwarded-Proto`, upgrade WebSocket connections, and can serve `stk/static` directly. With Nginx:

```nginx
# Versioned static URLs (?v=<hash>) never change content; the rest revalidate.
map $arg_v $static_expires {
    '' epoch;
    default max;
}

location /static/ {
    alias /path/to/stk/stk/static/;
    expires $static_expires;
}

location / {
    proxy_pass http://127.0.0.1:5000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
}
```

`$connection_upgrade` needs the `map` block from `nginx/stk.conf`. Use Certbot or your own certificates for TLS.

## Troubleshooting

Requests rejected or OAuth redirecting to the wrong host: `STK_PUBLIC_URL` must match the URL users visit.

Database connection errors: check credentials in `.env` and that the URI uses `postgresql+asyncpg://`.

App not starting: `sudo journalctl -u <service>`. Missing `SECRET_KEY` or `SECURITY_PASSWORD_SALT` stops startup.

WebSockets not connecting: the proxy needs HTTP/1.1 with the `Upgrade` and `Connection` headers, and the browser origin must match the app's.
