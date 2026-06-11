# Security

STK owns authentication in-process. Do not replace it with a third-party auth service unless that is the explicit task.

Security invariants:
- Passwords are hashed through quart-security.
- Session auth is the default protected-route scheme.
- Admin routes require authenticated admin users.
- WebAuthn and TOTP are enabled framework features.
- Mutating admin actions should be activity logged.
- Do not expose secrets in generated artifacts.

When changing auth, inspect the route map, update tests or checks, and generate a project report.

## Agent Browser Login

Agent browser login is a development/testing-only session handoff. It is disabled by default and must never be enabled in production.

Required guards:

1. `STK_ENABLE_AGENT_LOGIN=1`
2. `STK_ENV=development` or `app.testing == true`
3. Signed short-lived token
4. Test user email ending in `@example.com`

If the feature is enabled outside development/testing, app startup fails.
