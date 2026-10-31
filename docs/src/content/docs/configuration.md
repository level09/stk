---
title: "Configuration"
description: "Every environment variable stk reads, and the app config values behind them"
---

`stk init` writes the app's `.env` from `.env-sample` with fresh secrets. stk's `Config` in `stk/settings.py` reads the variables below; `stk verify` fails if it starts reading one this page does not list. The app's own settings subclass it (`class Config(stk.Config)` in `myapp/settings.py`), read their own variables the same way, and override any default by attribute name.

## Core

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | required | Signs sessions; also derives the TOTP encryption key unless `SECURITY_TOTP_ENCRYPTION_KEYS` is set. Startup fails without it. |
| `SECURITY_PASSWORD_SALT` | required | Salt for password-related tokens. Startup fails without it. |
| `STK_ENV` | `production` | `development` enables development-only features such as agent login. |
| `QUART_DEBUG` | unset | `1` for the reloader and debug pages. Never in production. |
| `STK_PUBLIC_URL` | unset | Public origin, e.g. `https://app.example.com`. Restricts accepted hosts, builds OAuth callbacks, and sets the allowed WebSocket origin. Set it in production. |
| `SQLALCHEMY_DATABASE_URI` | SQLite at `instance/stk.db`, beside the app package | Use `postgresql+asyncpg://...` for PostgreSQL; plain `postgresql://` will not work. |
| `REDIS_URL` | unset | Stores sessions in Redis when the `full` extra is installed. `REDIS_SESSION` is read as a legacy alias. |

### Paths in the app's settings

`Config` has no project root setting. Build a path from the settings file itself:

```python
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # beside the app package


class Config(stk.Config):
    BLOB_DIR = os.environ.get("BLOB_DIR", str(PROJECT_ROOT / "instance" / "blobs"))
```

At runtime the app knows both: `app.root_path` is the app package and `app.instance_path` is `instance/` beside it, where the default SQLite database lives.

## Branding

| Variable | Default | Purpose |
|---|---|---|
| `APP_NAME` | `stk` | Page titles and exported recovery codes. |
| `APP_TAGLINE` | `Secure. Scalable. Swift.` | Sign-up panel heading. |
| `APP_DESCRIPTION` | empty | Sign-up panel text. |

See [Renaming Your App](/branding).

## Auth and sessions

| Variable | Default | Purpose |
|---|---|---|
| `SECURITY_REGISTERABLE` | `False` | Public password sign-up. Keep it off unless the app needs it. |
| `SECURITY_TOTP_ENCRYPTION_KEYS` | unset | Comma-separated Fernet keys, newest first, for TOTP seeds. Rotate with `stk protect-mfa`. |
| `SECURITY_WAN_RP_ID` | unset | Passkey relying party: your bare DNS name. |
| `SECURITY_WAN_EXPECTED_ORIGIN` | unset | Passkey origin: your HTTPS origin. |
| `SESSION_COOKIE_SECURE` | `True` | Set `False` only for local HTTP; under plain HTTP a secure cookie breaks login. |
| `SESSION_COOKIE_HTTPONLY` | `True` | |
| `SESSION_COOKIE_SAMESITE` | `Lax` | |
| `DISABLE_MULTIPLE_SESSIONS` | `False` | `True` logs out a user's other sessions on every login. |
| `STK_ENABLE_AGENT_LOGIN` | `False` | Test-only browser login for agents. Startup fails if it is on outside development or testing. |
| `STK_AGENT_LOGIN_MAX_TTL_SECONDS` | `60` | Longest lifetime `stk browser-token create` may issue. |

## OAuth

| Variable | Default | Purpose |
|---|---|---|
| `GOOGLE_AUTH_ENABLED` | `False` | Turn on Google login. |
| `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET` | unset | Google credentials. |
| `GOOGLE_OAUTH_REDIRECT_URI` | derived | Override the callback URL; normally built from `STK_PUBLIC_URL`. |
| `GITHUB_AUTH_ENABLED` | `False` | Turn on GitHub login. |
| `GITHUB_OAUTH_CLIENT_ID`, `GITHUB_OAUTH_CLIENT_SECRET` | unset | GitHub credentials. |
| `OAUTHLIB_INSECURE_TRANSPORT` | `0` | `1` allows OAuth over local HTTP. Development only. |

See [Authentication](/authentication#oauth).

## Mail

| Variable | Default | Purpose |
|---|---|---|
| `MAIL_SERVER` | unset | SMTP host; port 465 with SSL. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | unset | SMTP credentials. |
| `SECURITY_EMAIL_SENDER` | `info@domain.com` | From address. |

## Docker Compose

Read by the app's `docker-compose.yml`, not by the app: `DB_ADMIN_PASSWORD`, `DB_PASSWORD`, `REDIS_PASSWORD`, `STK_HOST`, `TLS_CERTIFICATE`, `TLS_PRIVATE_KEY`, and `DOCKER_UID`. See [Deployment](/deployment#docker-compose).

## App config values

Some limits are app config only, with no environment variable. Set them on your app's `Config` class:

| Key | Default | Purpose |
|---|---|---|
| `STK_AUTH_ATTEMPT_LIMIT` | `10` | Login attempts per IP per minute. |
| `STK_AUTH_REQUEST_LIMIT` | `120` | Auth requests per IP per minute. |
| `STK_MCP_REQUEST_LIMIT` | `120` | MCP requests per agent token per minute. |
| `STK_SMOKE_SKIP` | `()` | Parameterless GET paths `stk smoke` must not visit, such as a link that needs a secret key. WebSockets and `@csrf_exempt` webhooks are skipped already. |
| `STK_CLI_SECTIONS` | `()` | Your commands' groups in `stk --help`, as `[("Runs", ["worker", "enrich"])]`, listed after stk's. Commands in no group appear under Other. |
| `STK_WS_ALLOWED_ORIGINS` | `STK_PUBLIC_URL` | WebSocket origins to accept. |
| `STK_WS_CONNECTIONS_PER_USER` | `5` | Open sockets per user. |
| `STK_WS_MAX_CONNECTIONS` | `1000` | Open sockets per worker. |
| `STK_WS_MESSAGE_LIMIT` | `60` | Client messages per socket per minute. |
| `STK_WS_MESSAGE_SIZE` | `65536` | Largest client message in bytes. |
| `STK_WS_QUEUE_SIZE` | `32` | Outgoing messages buffered before a slow client is dropped. |
| `STK_WS_AUTH_INTERVAL` | `5` | Seconds between session rechecks on an open socket. |
