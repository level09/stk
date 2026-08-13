---
name: stk-deploy
description: Deploy an stk app to production on a fresh VPS with HTTPS, systemd, and a hardened OS. Use when taking an stk app live, deploying to a server, or setting up production hosting for a domain.
argument-hint: "[domain]"
---

# Deploy stk App to Production

One-shot production install via `deploy.sh` (framework root). Installs Caddy
(auto-TLS, security headers, static caching), a systemd service, a non-root app
user, generated secrets, and hardens the box (SSH key-only, fail2ban, ufw).
SQLite by default, PostgreSQL+Redis optional.

## Prerequisites

1. Fresh Ubuntu/Debian VPS with root SSH access.
2. DNS A record for the domain pointing at the server (Caddy needs it for TLS).
3. App repo pushed to GitHub **and public**, or see the private-repo note below.

## Install (non-interactive)

Run from your machine against the server, or on the server as root:

```bash
wget -qO /tmp/deploy.sh https://raw.githubusercontent.com/level09/stk/master/deploy.sh
sudo DOMAIN=example.com REPO=<github-user>/<repo> bash /tmp/deploy.sh
```

Env vars: `DOMAIN` (required), `REPO` (default `level09/stk`), `BRANCH`
(default `master`), `DB=sqlite|postgres`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`,
`PYTHON_PORT` (default 5000), `SKIP_SSL=true` (HTTP only, no TLS).

Ends at a live `https://<domain>` with an admin login. Credentials are saved
on the server at `/home/<app-user>/.credentials`.

## Hard warnings

- **Never re-run deploy.sh on a live app.** It is install-only: it deletes and
  re-clones the app directory. With SQLite the database is
  `instance/stk.db` *inside* that directory, so a re-run destroys production
  data. Use the update flow below.
- **Private repos fail silently at the clone step**: the script clones over
  plain HTTPS. Either make the repo public, or pre-seed a read-only GitHub
  token on the server and clone via `git@github.com:` manually first.

## Update flow (every deploy after the first)

```bash
ssh <app-user>@<domain>
cd ~/<domain>
git pull
uv sync --frozen --no-dev
uv run --no-sync stk db upgrade   # only if models changed
sudo systemctl restart <domain>.service
```

The app user's sudoers allows managing only its own service.

## Verify

- `curl -I https://<domain>` returns 200/302 with the security headers.
- Log in as admin, create a throwaway record, restart the service, confirm it
  survives (proves the DB path).
