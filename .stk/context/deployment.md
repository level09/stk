# Deployment

Production installs use `deploy.sh` (repo root) on a fresh Ubuntu 22.04/24.04 VPS. It is bare-metal: systemd + uvicorn behind Caddy, no Docker. `setup.sh` is local dev only.

Run as root:

```bash
sudo DOMAIN=example.com bash deploy.sh
```

Config via env vars: `DOMAIN` (required; an IP works with `SKIP_SSL=true`), `REPO` (default `level09/stk`), `BRANCH` (`master`), `DB` (`sqlite` default, `postgres` adds Redis + the `full` extra), `ADMIN_EMAIL`, `ADMIN_PASSWORD` (generated if unset), `SKIP_SSL`, `PYTHON_PORT` (`5000`).

What it produces:

- App at `/home/<user>/<domain>` owned by a dedicated user (`<user>` = domain's first label), deps installed with `uv sync --frozen --no-dev --python 3.13` (uv downloads its own CPython; no system Python or PPAs).
- systemd unit `<domain>.service` running `.venv/bin/uvicorn run:app --host 127.0.0.1 --port <PYTHON_PORT>`, `Restart=always`.
- Caddy vhost with auto-SSL (or `:80` when `SKIP_SSL=true`), security headers, static served from `<app>/stk/static`, JSON logs at `/var/log/caddy/<domain>.log`.
- `.env` with generated `SECRET_KEY`, `SECURITY_PASSWORD_SALT`, `SECURITY_TOTP_SECRETS`; `SESSION_COOKIE_SECURE` is `True` only when SSL is on (setting it under plain HTTP breaks login).
- Admin credentials at `/home/<user>/.credentials` (chmod 600).
- Hardening: UFW (22/80/443), fail2ban, key-only SSH, sudoers scoped to the one app service.

Verify a deploy:

```bash
curl -s -o /dev/null -w "%{http_code}" http://<domain-or-ip>/   # expect 200
systemctl is-active <domain>.service
```

Then log in at `/login` with the credentials file and, for behavioral confidence, run `uv run quart smoke` locally against the same revision.

Update a deployed app (as the app user, in the app dir):

```bash
git pull && uv sync --frozen --no-dev && uv run quart db upgrade && sudo systemctl restart <domain>.service
```
