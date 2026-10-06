"""Local security review probes. Uses only an in-memory database and mocked IdPs."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pyotp
from quart import g, request
from quart_security import hash_password
from quart_session.sessions import RedisSessionInterface
from sqlalchemy import select

import stk.extensions as ext
from stk.app import create_app
from stk.public.views import handle_oauth_callback
from stk.settings import Config
from stk.user.models import Activity, Base, OAuth, Role, User


class ReviewConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///:memory:"
    SESSION_TYPE = None
    SECURITY_COOKIE_SECURE = False
    QUART_RATE_LIMITER_ENABLED = False
    SECURITY_PASSWORD_BREACH_CHECK = False
    GOOGLE_AUTH_ENABLED = False
    GITHUB_AUTH_ENABLED = False


PASSWORD = "ReviewPassword123!"
results = {}


async def login(client, email="admin@example.com", password=PASSWORD):
    await client.get("/login")
    async with client.session_transaction() as cookie:
        csrf = cookie["_csrf_token"]
    response = await client.post(
        "/login", form={"email": email, "password": password, "csrf_token": csrf}
    )
    assert response.status_code == 302


async def csrf_token(client, path="/login"):
    await client.get(path)
    async with client.session_transaction() as cookie:
        return cookie["_csrf_token"]


async def main():
    app = create_app(ReviewConfig)

    # Probe the host's provider-data boundary without a real IdP or network.
    @app.get("/_review/oauth")
    async def oauth_fixture():
        email = request.args.get("email", "user@example.com")
        return await handle_oauth_callback(
            "google",
            {"access_token": "fixture-token"},
            {
                "sub": f"fixture-google-id-{email}",
                "email": email,
                "email_verified": request.args.get("verified") == "true",
            },
        )

    async with ext.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with ext.async_session_factory() as db:
        role = Role(name="admin")
        admin = User(
            email="admin@example.com",
            active=True,
            password=hash_password(PASSWORD, app=app),
        )
        admin.roles.append(role)
        user = User(
            email="user@example.com",
            active=True,
            password=hash_password(PASSWORD, app=app),
        )
        db.add_all([admin, user])
        await db.commit()
        admin_id, user_id = admin.id, user.id

    anonymous = app.test_client()
    results["anonymous_admin_api"] = (
        await anonymous.get("/api/users", headers={"Content-Type": "application/json"})
    ).status_code
    admin_client = app.test_client()
    await login(admin_client)
    results["api_no_csrf_foreign_origin"] = (
        await admin_client.post(
            "/api/role/",
            json={"item": {"name": "review-role"}},
            headers={"Origin": "https://other.example"},
        )
    ).status_code
    results["api_simple_content_type"] = (
        await admin_client.post(
            "/api/role/",
            data='{"item":{"name":"simple-content"}}',
            headers={"Content-Type": "text/plain", "Origin": "https://other.example"},
        )
    ).status_code
    results["login_without_csrf"] = (
        await anonymous.post("/login", form={"email": "a@example.com", "password": "x"})
    ).status_code
    results["clear_admin_roles_response"] = (
        await admin_client.post(f"/api/user/{admin_id}", json={"item": {"roles": []}})
    ).status_code
    results["admin_access_after_clear_roles"] = (
        await admin_client.get("/api/users")
    ).status_code

    user_client = app.test_client()
    await login(user_client, "user@example.com")
    results["non_admin_api"] = (await user_client.get("/api/activities")).status_code
    async with user_client.websocket(
        "/ws", headers={"Origin": "https://other.example"}
    ) as ws:
        results["websocket_foreign_origin"] = json.loads(await ws.receive())["type"]
        await admin_client.post("/api/role/", json={"item": {"name": "another-role"}})
        results["non_admin_receives_admin_event"] = json.loads(
            await asyncio.wait_for(ws.receive(), 2)
        )
        csrf = await csrf_token(user_client)
        await user_client.post("/logout", form={"csrf_token": csrf})
        async with app.test_request_context("/"):
            async with ext.async_session_factory() as db:
                g.db_session = db
                await Activity.register(admin_id, "Review event after logout", {})
                await db.commit()
        results["websocket_receives_after_logout"] = json.loads(
            await asyncio.wait_for(ws.receive(), 2)
        )

    app.config["DISABLE_MULTIPLE_SESSIONS"] = True
    first = app.test_client()
    await login(first)
    csrf = await csrf_token(first, "/change")
    response = await first.post(
        "/change",
        form={
            "password": PASSWORD,
            "new_password": "ReplacementPassword123!",
            "new_password_confirm": "ReplacementPassword123!",
            "csrf_token": csrf,
        },
    )
    assert response.status_code == 302
    await login(app.test_client(), password="ReplacementPassword123!")
    results["single_session_after_password_rotation"] = (
        await first.get("/dashboard/")
    ).status_code

    async with ext.async_session_factory() as db:
        user = await db.get(User, user_id)
        user.tf_primary_method = "authenticator"
        user.tf_totp_secret = pyotp.random_base32()
        await db.commit()
    oauth_client = app.test_client()
    results["unverified_oauth_link_response"] = (
        await oauth_client.get("/_review/oauth")
    ).status_code
    results["oauth_access_without_totp"] = (
        await oauth_client.get("/dashboard/")
    ).status_code
    async with ext.async_session_factory() as db:
        linked = await db.scalar(select(OAuth).where(OAuth.provider == "google"))
        results["unverified_email_linked_to_existing_user"] = linked.user_id == user_id

    # An invalid/missing state must be rejected before token exchange.
    token_client = AsyncMock()
    token_client.fetch_token.return_value = {"access_token": "fixture-token"}
    http = AsyncMock()
    http.__aenter__.return_value = http
    response = type(
        "ProfileResponse",
        (),
        {
            "json": lambda self: {
                "id": "fixture-github-id",
                "email": "user@example.com",
                "name": "Fixture",
            }
        },
    )()
    http.get.return_value = response
    with (
        patch("stk.public.views.get_github_client", return_value=token_client),
        patch("stk.public.views.httpx.AsyncClient", return_value=http),
    ):
        callback_client = app.test_client()
        await callback_client.get("/login/github/callback?code=fixture-code")
        results["missing_oauth_state_token_exchange_calls"] = (
            token_client.fetch_token.await_count
        )
        results["disabled_oauth_callback_access"] = (
            await callback_client.get("/dashboard/")
        ).status_code

    registration_client = app.test_client()
    csrf = await csrf_token(registration_client, "/register")
    response = await registration_client.post(
        "/register",
        form={
            "email": "victim@example.com",
            "password": PASSWORD,
            "password_confirm": PASSWORD,
            "csrf_token": csrf,
        },
    )
    assert response.status_code == 302
    victim_client = app.test_client()
    await victim_client.get("/_review/oauth?email=victim@example.com&verified=true")
    attacker_client = app.test_client()
    await login(attacker_client, "victim@example.com")
    results["pre_registered_password_after_verified_oauth"] = (
        await attacker_client.get("/dashboard/")
    ).status_code

    class MemoryRedis:
        def __init__(self):
            self.values = {}

        async def get(self, key):
            return self.values.get(key)

        async def setex(self, name, value, time):
            self.values[name] = value

        async def delete(self, key):
            self.values.pop(key, None)

    # Use the actual Redis session interface with only its storage replaced.
    app.session_interface = RedisSessionInterface(
        redis=MemoryRedis(),
        key_prefix="session:",
        use_signer=False,
        permanent=True,
        SESSION_PROTECTION=False,
        SESSION_REVERSE_PROXY=False,
        SESSION_STATIC_FILE=False,
    )
    attacker = app.test_client()
    await attacker.get("/login")
    known_sid = next(c.value for c in attacker.cookie_jar if c.name == "session")
    victim = app.test_client()
    victim.set_cookie("localhost", "session", known_sid)
    await login(victim, password="ReplacementPassword123!")
    results["redis_sid_preserved_on_login"] = any(
        c.name == "session" and c.value == known_sid for c in victim.cookie_jar
    )
    results["pre_login_redis_cookie_access_after_victim_login"] = (
        await attacker.get("/dashboard/")
    ).status_code

    await ext.engine.dispose()
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
