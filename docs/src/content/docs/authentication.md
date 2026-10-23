---
title: "Authentication"
description: "User authentication and security features in stk"
sidebar:
  label: "Authentication"
---

## Overview

stk builds authentication on quart-security: session auth, roles, TOTP two-factor, WebAuthn passkeys, recovery codes, and opt-in Google and GitHub OAuth. Production requirements are in [SECURITY.md](https://github.com/level09/stk/blob/master/SECURITY.md); the [deployment guide](/deployment) covers the settings you must set.

## Accounts and passwords

Public password registration is disabled by default. Set `SECURITY_REGISTERABLE=true` only if your app needs it. Create users from the CLI instead:

```bash
uv run stk install                          # admin user with the admin role
uv run stk create -e user@example.com       # prompts for a password
uv run stk add-role -e user@example.com -r editor
uv run stk reset -e user@example.com        # prompts for a new password
```

New passwords are hashed with Argon2id and must be at least 12 characters. Legacy hashes still verify and are upgraded on login. Password creation and reset also check the password against the Have I Been Pwned breach service; if that service is unreachable the password is accepted, so monitor for those failures.

After 5 failed logins an account is locked for 15 minutes (quart-security's `SECURITY_LOGIN_MAX_ATTEMPTS` and `SECURITY_LOCKOUT_MINUTES` defaults).

## Two-factor and passkeys

TOTP authenticator apps are the enabled second factor. Three single-use recovery codes are generated per user, hashed at rest, and shown only once. WebAuthn passkeys work as a first factor or as a second factor. Managing 2FA, recovery codes, or passkeys requires a fresh session: a login within the last 60 minutes, otherwise the request gets a 401.

TOTP seeds are encrypted at rest. By default the key is derived from `SECRET_KEY`, so changing `SECRET_KEY` breaks existing 2FA unless you keep the old key. For independent rotation, set `SECURITY_TOTP_ENCRYPTION_KEYS` to a comma-separated list of Fernet keys, newest first:

```bash
uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

The first key encrypts new data and every listed key can decrypt. After upgrading or rotating keys, run `uv run stk protect-mfa` to encrypt legacy seeds and re-encrypt existing ones with the current key. Store the keys separately from database backups. A wrong key fails closed.

Passkeys need `SECURITY_WAN_RP_ID` set to your DNS name and `SECURITY_WAN_EXPECTED_ORIGIN` set to your HTTPS origin.

## OAuth

Google and GitHub login are off until enabled:

```bash
GOOGLE_AUTH_ENABLED=true
GOOGLE_OAUTH_CLIENT_ID=your_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret

GITHUB_AUTH_ENABLED=true
GITHUB_OAUTH_CLIENT_ID=your_client_id
GITHUB_OAUTH_CLIENT_SECRET=your_client_secret
```

Callbacks are `/login/google/callback` and `/login/github/callback`, built from `STK_PUBLIC_URL` when it is set. Requested scopes are `openid profile email` for Google and `read:user user:email` for GitHub. Each login uses single-use state and PKCE. Only verified provider emails are accepted, a matching local email is never linked automatically, and a user with local 2FA must still complete it. Locked accounts cannot sign in through OAuth either.

## Protecting routes

```python
from quart_security import auth_required, roles_required

@app.route("/admin")
@auth_required("session")
@roles_required("admin")
async def admin_dashboard():
    return "Admin only content"
```

To protect a whole blueprint, apply the decorator to its `before_request` hook, as `stk/portal/views.py` does:

```python
@portal.before_request
@auth_required("session")
async def before_request():
    pass
```

## CSRF and logout

Every POST, PUT, PATCH, and DELETE request needs the session CSRF token, in a form field or the `X-CSRFToken` header. The shared layout configures Axios for you. Third-party webhooks that have no session can opt out per view with `csrf_exempt` from `stk.security`, placed under the route decorator; such a view must authenticate the caller itself, for example with an HMAC signature.

Logout is POST-only. Use `layoutMixin.logout()`; a plain link to `/logout` returns 405.

## Sessions and rate limits

`PERMANENT_SESSION_LIFETIME` is 3600 seconds. Cookies default to `Secure`, `HttpOnly`, and `SameSite=Lax`, controlled by `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, and `SESSION_COOKIE_SAMESITE`. Sessions are stored in Redis when `REDIS_URL` is set and the `full` extra is installed, otherwise in the cookie. Each login is recorded with IP and device in the `Session` table. `DISABLE_MULTIPLE_SESSIONS=true` logs out other sessions on every login.

Auth endpoints are rate limited per IP with fixed one-minute windows stored in the database, so limits hold across workers. The defaults are 10 authentication attempts and 120 authentication requests per minute, set by the `STK_AUTH_ATTEMPT_LIMIT` and `STK_AUTH_REQUEST_LIMIT` app config values. Limits depend on a trustworthy client IP, so behind a proxy trust forwarded headers only from that proxy.

## Troubleshooting

OAuth failing: check that the callback URL registered with the provider matches `STK_PUBLIC_URL` plus the callback path, and that the provider account has a verified email.

TOTP codes rejected: check the server clock, and that `SECRET_KEY` or `SECURITY_TOTP_ENCRYPTION_KEYS` still holds the key the seeds were encrypted with.

Passkeys failing: `SECURITY_WAN_RP_ID` and `SECURITY_WAN_EXPECTED_ORIGIN` must match the host in the browser.

Logged out too soon: check `PERMANENT_SESSION_LIFETIME`, and for Redis sessions, `REDIS_URL`.
