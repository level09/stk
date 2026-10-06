# stk production security and Enferno parity review

Reviewed 2026-10-06. Original verdict: do not approve stk 15.0.0 for general production use yet.
The earlier release checks passed, but they did not cover the failures below.
The original review below describes version 15.0.0. The version 16 remediation section records subsequent fixes. No existing database or deployment was changed.

## Scope and evidence

- stk: `47506bf8f7db3f1b29ab61537e74cbc1e3477155`, version 15.0.0.
- quart-security: the published 2.0.0 package installed in stk's environment.
- Enferno: `0cb2a925118b88cf6a85c233df75e26a6eb2e79d`, Flask-Security-Too 5.9.0.
- Inspected application routes, models, auth forms, session handlers, scaffolding,
  dependency code, Docker, Nginx, Caddy installer, and deployment documentation.
- Ran real local login, API, password-change, and WebSocket paths against an
  in-memory SQLite database. OAuth exchanges and provider claims were mocked.
- Tested the actual quart-session Redis interface with in-memory storage replacing
  only Redis I/O. No Redis server was contacted. Enferno used its actual SQLAlchemy
  server-session interface with an in-memory database.
- stk's existing 101 tests pass. This does not invalidate the failing probes.
- Dependency scans used pinned exports, with dependency resolution disabled.
  Base stk: 58 packages. stk with `full`: 60. Enferno with `full`: 74.
- No live provider account, deployment, PostgreSQL server, TLS proxy, hardware
  passkey, browser cookie injection, or hostile browser origin was tested.

Probe code and results are in `security-review/2026-10-06-reproduce.py`,
`security-review/2026-10-06-results.json`, `security-review/2026-10-06-enferno.py`,
and `security-review/2026-10-06-enferno-results.json`.

## Findings

### 1. P1: OAuth callbacks accept a missing state

Source: `stk/public/views.py:227-228` and `:309-312`.

```python
state = request.args.get("state")
if state != session.pop("oauth_state_google", None):
    ...
```

When the query and cookie state are both missing, `None == None`, so the callback
continues to exchange the code. The GitHub probe made one token-exchange call and
created an authenticated session without an OAuth initiation step. Callback routes
also remain active when the provider's enabled flag is false. Real redemption
still requires valid provider credentials and a usable authorization code.

Impact: login CSRF and authorization-code injection when OAuth is configured.
The absence of PKCE and an OIDC nonce leaves no independent transaction binding
in this host implementation. A disabled provider with retained credentials is not
fully disabled at the callback.

Fix: require non-empty received and stored state, compare them safely, and bind
the transaction to the browser. Reject disabled providers at both entry points.
Use Authlib's supported OAuth/OIDC integration with PKCE and nonce validation
rather than constructing the full flow manually.

Enferno uses Flask-Dance for state handling. This review did not simulate a live
Flask-Dance callback; do not infer equivalent callback safety solely from its use.

### 2. P1: Email-based OAuth linking enables account pre-hijacking

Source: `stk/public/views.py:112-119`, `:145-158`, `:337-346`;
`stk/settings.py:36-38`; quart-security `views.py:434-450`.

```python
existing_user = ...select(User).filter_by(email=email)...
oauth_account = OAuth(..., user=existing_user)
await _security.login_user(existing_user)
```

Reproduction: register `victim@example.com` with an attacker-known password;
sign in through a mocked provider that reports that email as verified; then sign
in using the original password. Both sessions receive dashboard HTTP 200.
Registration does not require mailbox verification, and automatic linking retains
the pre-registered password.

The handler also linked `email_verified=False` to an existing user. Google email
verification and GitHub email verification flags are not checked. The GitHub
fallback selects a primary address without requiring `verified`. This proves the
host accepts unverified claims, not that a particular live IdP currently allows
an attacker to claim any arbitrary target email.

Fix: do not link by email alone. Link while authenticated to the existing account
with a fresh verification step, or require proof of mailbox/account ownership
through a defined recovery flow. Validate provider subject and verified email.
Choose a verified primary GitHub address from the email endpoint. Address
pre-registered accounts explicitly; a verified IdP claim alone does not remove an
attacker's existing local credential.

Enferno shares email-only linking and lacks a verification check in
`enferno/public/views.py:160-191`. Its local probe also linked an existing account.
The complete pre-registration sequence was executed on stk only.

### 3. P1: OAuth skips the account's local MFA policy

Source: `stk/public/views.py:139-143`, `:148-159`, `:170-172`.

All three OAuth success paths call `login_user()` directly. The account's TOTP
setting is not checked. A user with an enrolled authenticator received dashboard
HTTP 200 after the mocked OAuth callback without entering a TOTP code.

Fix: route federated login through the same pending-MFA flow as password login,
or define and enforce an explicit trusted-IdP assurance policy. Do not silently
treat an arbitrary provider login as satisfaction of the local authenticator.

Enferno's direct `flask_security.login_user()` calls have the same observed result.
This is a shared host integration defect, not evidence that the library's normal
password login skips MFA.

### 4. P1: Redis login retains a fixable server-session ID

Source: `stk/settings.py:69-74`; quart-security `core.py:256-263`;
quart-session `sessions.py:124-148`, `:168-191`.

```python
session.clear()
session["_user_id"] = user_id
session["_id"] = token
```

The library rotates its internal authentication token but leaves Redis
`session.sid` unchanged. The probe copied an existing anonymous SID to a victim
client. After the victim logged in, the original client received dashboard HTTP
200 using that same pre-login SID. Redis resolves both clients to the newly
authenticated record.

Exploit prerequisite: an attacker must plant or otherwise control a valid
pre-login session cookie used by the victim. Cookie injection in a real browser
was not demonstrated. Random SIDs prevent guessing but do not fix reuse of a
known valid SID. Signing that same SID alone would not fix this either.

Fix: regenerate the server-session ID at authentication and privilege transitions,
delete the old backend record, and preserve only required pre-login data. Test
both the internal authentication token and the external cookie SID.

Enferno also retained its SQLAlchemy session SID and allowed the copied pre-login
cookie after authentication in the local probe. Its strong session protection
does not stop clients that match the tested IP/device context. Redis behavior was
not independently tested for Enferno.

### 5. P1: Clearing roles leaves the admin role active

Source: `stk/user/models.py:124-130`; `stk/user/views.py:80-98`.

```python
if "roles" in json_dict:
    role_ids = [r.get("id") for r in json_dict["roles"]]
    if role_ids:
        self.roles = ...
```

An admin update with `{"item":{"roles":[]}}` returns HTTP 200, but the account
still accesses the admin API. Empty lists never reach relationship assignment.
This is a permission-revocation failure, not an anonymous privilege escalation.

Fix: assign an empty relationship when the field is present and empty. Keep the
existing relationship only when the field is absent. Verify the affected user's
next authenticated request is denied.

Enferno has the same bug at `enferno/user/models.py:108-114`, confirmed by its probe.

### 6. P1: Docker publishes databases with fallback credentials

Source: `docker-compose.yml:7-11`, `:23-27`, `:45-53`.

```yaml
command: redis-server --requirepass ${REDIS_PASSWORD:-verystrongpass}
ports:
  - '6379:6379'
```

PostgreSQL similarly uses `verystrongpass` and publishes 5432. With omitted
secrets and a reachable host, these are externally exposed services using public
credentials. The app port 8000 also permits bypass of protections added only at
Nginx. This is a template defect; no running deployment was inspected.

Fix: require explicit secrets with Compose's `:?` form. Keep data services on
the internal network and restrict any maintenance publication to loopback. Expose
the application only through the intended TLS proxy. Require an explicit migration
step before application startup; the Docker command does not apply migrations.

Enferno already requires DB/Redis secrets and does not publish their ports.
Its app port remains externally published, so that part is shared.

### 7. P2: The dependency lock has known advisories

The base and `full` stk scans each report 37 entries, which deduplicate to 21
package/advisory-ID pairs across six packages. The scanner exits 1. Audit JSON
files are saved alongside the probes. This finding replaces any earlier claim
that this locked dependency set has no known advisories.

| Package | stk lock | Scanner's fixed version | Exposure assessment |
| --- | --- | --- | --- |
| anyio | 4.13.0 | 4.14.2 | Review outbound TLS and affected IDNA paths. Fixed OAuth endpoints use ASCII hosts. |
| h2 | 4.3.0 | 4.4.1 | Installed through Hypercorn. Production's supplied Uvicorn path does not prove an HTTP/2 exploit. |
| hpack | 4.1.0 | 4.2.0 | HTTP/2 header decoder denial of service; relevant when affected HTTP/2 paths are exposed. |
| pillow | 12.2.0 | 12.3.0 | Current auth path generates QR images. No uploaded-image decoding endpoint was found. |
| pyasn1 | 0.6.3 | 0.6.4 | Review certificate/ASN.1 decoding paths; hostile input reachability was not demonstrated. |
| werkzeug | 3.1.8 | 3.1.9 | Reported device-name issue is specific to Windows/NTFS. Supplied Linux deployment is outside that condition. |

Enferno's locked `full` set scanned 74 packages with no known advisories reported.
That is a point-in-time scanner result, not a proof of secure code. In particular,
Enferno pins Pillow 12.3.0, pyasn1 0.6.4, and Werkzeug 3.1.9.

Fix: update the affected lock entries to patched versions, test compatibility,
and scan the resulting lock. Verify actual server/backend reachability before
assigning deployed exploit severity. The present finding does not claim all 21
advisories are exploitable in stock stk.

### 8. P2: Session rotation escapes single-session enforcement

Source: `stk/user/models.py:295-300`; `stk/user/views.py:275-299`, `:303-320`;
quart-security `core.py:273-277`.

The library replaces `session['_id']` after password/MFA/passkey profile changes.
stk creates tracking rows at login but does not update them for this replacement.
Single-session mode deletes authentication tokens found in those tracking rows.
The new token is absent from the rows and survives the deletion.

Reproduction: enable single-session mode, login, change the password through
`/change`, then login with a second client. The first client still gets dashboard
HTTP 200. The existing ordinary two-login test passes because it does not rotate
the first session between logins.

Fix: use a canonical session-revocation operation that covers current auth state,
and keep tracking synchronized at every rotation. Do not infer the complete set
of valid sessions from historical login rows.

Enferno's single-session probe retained the previous session even without a
password change. `Session.is_active` is tracking state, not a loader-level control.
stk is better on the simple path but does not yet implement the promised invariant.

### 9. P2: WebSocket access does not match HTTP access

Source: `stk/websocket.py:24-33`, `:36-63`; `stk/user/models.py:225-232`.

Three independent gaps share this channel:

- An ordinary user receives `Role Create` audit events with the actor's user ID
  despite receiving HTTP 403 from `/api/activities`. The payload does not include
  the full activity record, but leaks restricted event metadata.
- The open socket continues receiving events after logout. Authentication,
  expiry, account status, roles, and token revocation are not rechecked.
- A handshake bearing an unrelated Origin is accepted when a valid cookie is
  supplied. Browser exploitation depends on cookie policy and site relationships;
  the test client does not enforce browser SameSite restrictions.

The queue is also unbounded, and no socket connection limit is present. Slow
consumers or many connections can consume memory. This resource risk was found
by inspection, not by a load test.

Fix: validate allowed origins; apply event-level authorization; bind connections
to session tokens; close on logout/revocation/expiry; bound queues and connections.
Send audit events only to the users allowed to inspect them. Do not broadcast an
uncommitted audit event as though its transaction succeeded.

Enferno has no matching WebSocket feature in the reviewed tree. HTTP auth parity
cannot cover this extra stk surface.

### 10. P2: Custom API mutations lack an explicit CSRF control

Source: `stk/app.py:100-124`; `stk/user/views.py:60-219`;
`stk/templates/layout.html:172`; `stk/scaffold/templates.py:95` onward.

An authenticated admin POST with JSON, no CSRF token, and an unrelated Origin
creates a role with HTTP 200. The normal auth forms reject missing CSRF tokens
with HTTP 400, so their protection does not extend to custom API mutations.
stk does not configure Axios's CSRF header as Enferno does.

Important limit: the JSON request above is a server-side probe, not a proven
cross-origin browser exploit. JSON generally requires a CORS preflight, and stock
stk does not enable permissive CORS. SameSite=Lax also blocks many cross-site
cookie requests. A simple text/plain request produced HTTP 500 and no role
creation. These constraints reduce current browser exploitability. Do not report
this as a demonstrated drive-by account takeover.

Fix: enforce CSRF centrally for session-authenticated mutation routes and send the
token through Axios, or implement an explicit, tested Origin/Fetch-Metadata/custom
header policy with tightly controlled CORS. Return 400/415 for invalid bodies.
Apply the same policy to generated endpoints.

Enferno's `CSRFProtect` rejects the equivalent tokenless JSON request with HTTP
400. Its layout supplies `X-CSRFToken`. This is a clear protection-parity gap.

## Production configuration and reliability gaps

These are inspection findings and deployment conditions, not separately proven
exploits:

- `stk/app.py:117-120` uses the limiter's default in-memory store. The dependency
  keys limits by endpoint and remote address. Limits are neither shared between
  workers nor applied to custom OAuth routes. Use shared storage and explicit
  per-source/global policies. Account lockout protects another dimension.
- The Caddy installer binds Uvicorn to loopback, uses secure cookies by default,
  generates secrets, sets `.env` mode 600, and supplies basic security headers.
  These controls are stronger than the supplied Docker/Nginx sample.
- `nginx/stk.conf` has no TLS, WebSocket upgrade headers, forwarded scheme,
  security response headers, or limits. The deployment documentation has some
  missing proxy settings, but the sample does not apply them automatically.
- OAuth tracking trusts arbitrary forwarding headers in `get_real_ip()`. That is
  audit spoofing if the app is directly reachable; it is not the limiter's key.
  Define the trusted proxy boundary and test the actual ASGI scope behind it.
- WebAuthn derives RP/origin from request host/scheme unless explicitly configured.
  The installer does not set explicit RP/origin values. Verify canonical HTTPS
  origins and proxy handling with a real browser and passkey.
- Stock registration is public and mailbox confirmation is disabled in both
  projects. Closed SaaS deployments must set a clear registration/verification
  policy; those defaults contribute to finding 2.
- Admin user creation/update bypasses the library's normal password-length and
  breach validation. Dedicated admin reset checks length, but does not use the
  breach check. This inconsistency is shared in part with Enferno.
- stk selects `pbkdf2_sha512` despite the library's Argon2id default. Do not
  describe stk passwords as Argon2 by default. Benchmark and choose a password
  hashing policy intentionally. The custom change form also verifies passwords
  synchronously in the event loop before the library's async verification.
- Admin list queries accept unbounded `per_page`; Enferno uses `db.paginate()`.
  This is an authenticated resource risk, not an anonymous SQL injection.
- Redis/PostgreSQL concurrency, failover, restart recovery, and production load
  remain untested here. SQLite probes do not establish those guarantees.

## Parity summary

| Control | stk 15.0.0 | Reviewed Enferno |
| --- | --- | --- |
| Anonymous/admin HTTP access | Probes return 401/403 as expected | Admin blueprint decorators present |
| Auth form CSRF | Missing token rejected | Flask-WTF/Flask-Security |
| Custom mutation CSRF | Tokenless JSON accepted | Equivalent request rejected |
| Empty role removal | Admin access persists | Same confirmed defect |
| OAuth email linking | Unsafe automatic linking | Same integration pattern and local result |
| Local MFA after OAuth | Skipped | Same local result |
| External server-session SID rotation | Redis SID retained | SQLAlchemy SID retained |
| Single-session control | Simple path covered; rotation path fails | Previous session persists in probe |
| Logout of copied cookie | Existing stk regression passes | Remember-cookie fix present; not fully reprobed here |
| Password/MFA/passkey HTTP revocation | Shared library state and uniquifier rotation | Flask-Security controls plus host integration |
| Socket origin/auth/event isolation | Gaps confirmed | No equivalent surface |
| Docker DB/Redis credentials and ports | Fallback secrets and published ports | Required secrets, internal data ports |
| Locked production advisory scan | 21 distinct IDs across 6 packages | No known advisories in 74-package export |

Matching Enferno's shared defects would not make stk production-safe.

## Minimum release gate

1. Fix OAuth state, account linking, and MFA policy. Test rejected callbacks before
   any token exchange and a full pre-registration/account-link sequence.
2. Rotate external server-session IDs. Prove old anonymous and authenticated SIDs
   fail after authentication/privilege changes on a real Redis backend.
3. Fix empty-role revocation and rotated single-session tracking. Test the next
   HTTP request, not just database flags.
4. Restrict WebSocket events, origins, and lifetime. Test logout, password change,
   deactivation, role removal, expiry, and slow consumers.
5. Add a defined global mutation CSRF policy; remove Docker credential fallbacks
   and public data ports; patch and rescan the lock.
6. Run the full suite and browser smoke, then real PostgreSQL/Redis, TLS/proxy,
   OAuth provider, hardware passkey, and multi-worker checks in an explicitly
   approved staging environment. Do not claim these passed from this review.

## Reproduction

```bash
UV_CACHE_DIR=/tmp/stk-uv uv run --no-sync python security-review/2026-10-06-reproduce.py
UV_CACHE_DIR=/tmp/stk-uv uv run --no-sync --project /Users/level09/projects/enferno \
  python security-review/2026-10-06-enferno.py /Users/level09/projects/enferno
```

The first script intentionally sends a malformed body. Its HTTP 500 log is an
observed failure, not a failed script run. Both scripts print JSON and use only
test configuration. Their assertions validate setup; JSON values record defects.
They are review probes, not a replacement for regression tests after repair.

## Reference criteria

Read the raw upstream documents and advisory API records during this review:

- [OWASP OAuth guidance](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): bind authorization transactions and reject code injection.
- [OWASP CSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): use a defined browser request protection policy; SameSite and content type have limits.
- [OWASP WebSocket guidance](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html): origin checks, message authorization, session lifetime, and resource limits.
- [AnyIO advisory](https://github.com/advisories/GHSA-82r6-8w77-94w6): publication 2026-09-18 verified in the API record.
- [Werkzeug advisory](https://github.com/advisories/GHSA-g6x2-hccm-hh4m): publication 2026-10-05 verified in the API record; Windows/NTFS condition retained in the assessment.

Audit JSON contains the remaining advisory IDs, aliases, descriptions, and fixed
versions. Scanner severity labels are not used as a substitute for host exposure.


## Version 16 remediation

All ten confirmed framework findings were addressed in version 16.0.0. The original source line references and probe results above refer to the version 15 commit and remain historical evidence.

| Finding | Remediation | Verification |
| --- | --- | --- |
| Missing OAuth state | Atomic single-use SQL transaction, nonempty matching state, provider guard, PKCE | Missing state rejected before exchange; replay rejected |
| Email pre-hijacking | No automatic email linking; verified provider email required | Existing email never creates a link or authenticates; unverified email rejected |
| OAuth MFA bypass | Linked identities enter local MFA; locked and inactive accounts rejected | Pending MFA has no authenticated user; lockout and deactivation tests |
| Redis session fixation | Delete and replace external SID on login, logout, MFA transitions, and security state rotation | Real Redis tests reject copied anonymous and authenticated SIDs after login/password change |
| Empty role removal | Assign the queried role list even when empty | Next admin request returns 403 |
| Docker exposure | Required unique secrets, internal data ports, TLS ingress, restricted app database role | Compose configuration and Nginx TLS syntax pass; restricted role migrates PostgreSQL successfully |
| Vulnerable packages | Patched anyio, h2, hpack, Pillow, pyasn1, Werkzeug | Full runtime export including ASGI: no known advisories |
| Rotated single-session escape | Align tracking records with new canonical token and remove previous state | Password change followed by second login invalidates the first session |
| WebSocket gaps | Same-origin policy, repeated auth checks, bounded queues/connections/messages, explicit recipients; no automatic audit broadcasts | Foreign origin, logout, password change, inactive user, expiry, flood, slow consumer, isolation, and uncommitted-event checks |
| API CSRF | Global mutation protection; Axios header; form and passkey JSON token support | Missing/invalid tokens rejected; valid API and passkey contracts preserved |

Additional gaps addressed: shared atomic SQL rate limits across auth routes, trusted ASGI client IP rather than arbitrary headers, explicit production WebAuthn origin/RP settings, closed password registration default, admin password policy, async admin hashing, removal of duplicate synchronous verification, Argon2id default, bounded pagination, proxy upgrade/forwarding headers, smaller ingress bodies, response headers, and deployment instructions.

Verification on the final source:

- 127 unit tests: pass, with the real Redis test skipped in the default suite.
- 26 security tests against temporary PostgreSQL 17 and real Redis: pass, including concurrent shared limits. No existing services or databases used.
- SQLite and PostgreSQL migrations reach head without model drift. New restricted PostgreSQL app role is not a superuser and can apply all migrations.
- 26 isolated sanity checks: pass.
- Browser smoke: pass on home, login, authenticated dashboard, and admin users.
- Ruff lint, changed-file formatting, shell syntax, Compose configuration, and local Nginx TLS syntax: pass.
- Patched runtime advisory scan: no known vulnerabilities, with results in `security-review/2026-10-06-patched-audit.json`.
- CI includes PostgreSQL 15, real Redis, restricted-role migrations, and dependency advisory checks.

The source now meets the tested framework controls and improves on the confirmed shared Enferno defects. This is not a blanket approval of a production deployment. Live OAuth provider configuration, physical passkeys, deployed TLS/proxy behavior, certificate renewal, recovery/failover, and traffic capacity still need staging validation. Docker was not running locally, so the complete container stack was not started here. Existing OAuth links, saved provider tokens, and PostgreSQL role privileges need an operator review on upgrade. See `SECURITY.md`.
