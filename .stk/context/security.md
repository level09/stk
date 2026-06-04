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
