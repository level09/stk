"""Regression tests for host security controls, using isolated storage."""

import asyncio
import os
import secrets
import unittest
from unittest.mock import AsyncMock, patch

import pyotp
from quart import request
from quart.testing.connections import WebsocketDisconnectError
from quart_security import hash_password
from quart_session.sessions import RedisSessionInterface
from sqlalchemy import select

import stk.extensions as ext
from stk.app import create_app
from stk.public.views import handle_oauth_callback
from stk.settings import Config
from stk.user.models import Base, OAuth, Role, User


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "STK_TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:"
    )
    SESSION_TYPE = None
    SECURITY_COOKIE_SECURE = False
    SECURITY_PASSWORD_BREACH_CHECK = False
    QUART_RATE_LIMITER_ENABLED = False
    GOOGLE_AUTH_ENABLED = True
    GITHUB_AUTH_ENABLED = True


class MemoryRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, name, value, time):
        self.values[name] = value

    async def delete(self, key):
        self.values.pop(key, None)


class ProductionSecurityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app(TestConfig)

        @self.app.get("/_fixture/oauth")
        async def oauth_fixture():
            return await handle_oauth_callback(
                "google",
                {"access_token": "fixture"},
                {
                    "sub": "fixture",
                    "email": "user@example.com",
                    "email_verified": request.args.get("verified") == "true",
                },
            )

        if ext.engine.dialect.name == "postgresql":
            from sqlalchemy import text

            schema = "review_" + secrets.token_hex(8)
            async with ext.engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            ext.engine = ext.engine.execution_options(
                schema_translate_map={None: schema}
            )
            ext.async_session_factory.configure(bind=ext.engine)
        async with ext.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            admin = User(
                email="admin@example.com",
                active=True,
                password=hash_password("Password123!", app=self.app),
            )
            admin.roles.append(Role(name="admin"))
            user = User(
                email="user@example.com",
                active=True,
                password=hash_password("Password123!", app=self.app),
            )
            db.add_all([admin, user])
            await db.commit()
            self.admin_id, self.user_id = admin.id, user.id

    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def csrf(self, client, path="/login"):
        await client.get(path)
        async with client.session_transaction() as cookie:
            return cookie["_csrf_token"]

    async def login(self, client, email="admin@example.com", password="Password123!"):
        token = await self.csrf(client)
        response = await client.post(
            "/login", form={"email": email, "password": password, "csrf_token": token}
        )
        self.assertEqual(response.status_code, 302)

    async def test_api_requires_csrf(self):
        client = self.app.test_client()
        await self.login(client)
        response = await client.post("/api/role/", json={"item": {"name": "unsafe"}})
        self.assertEqual(response.status_code, 400)
        token = await self.csrf(client)
        response = await client.post(
            "/api/role/",
            json={"item": {"name": "safe"}},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 200)

    async def test_empty_roles_revoke_admin_access(self):
        client = self.app.test_client()
        await self.login(client)
        token = await self.csrf(client)
        response = await client.post(
            f"/api/user/{self.admin_id}",
            json={"item": {"roles": []}},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await client.get("/api/users")).status_code, 403)

    async def test_rotated_session_is_revoked_by_second_login(self):
        self.app.config["DISABLE_MULTIPLE_SESSIONS"] = True
        first = self.app.test_client()
        await self.login(first)
        token = await self.csrf(first, "/change")
        response = await first.post(
            "/change",
            form={
                "password": "Password123!",
                "new_password": "Replacement123!",
                "new_password_confirm": "Replacement123!",
                "csrf_token": token,
            },
        )
        self.assertEqual(response.status_code, 302)
        await self.login(self.app.test_client(), password="Replacement123!")
        self.assertNotEqual((await first.get("/dashboard/")).status_code, 200)

    async def test_oauth_does_not_link_existing_email(self):
        client = self.app.test_client()
        await client.get("/_fixture/oauth?verified=true")
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)
        async with ext.async_session_factory() as db:
            self.assertIsNone(await db.scalar(select(OAuth)))

    async def test_oauth_rejects_unverified_email(self):
        client = self.app.test_client()
        await client.get("/_fixture/oauth")
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)

    async def test_linked_oauth_requires_totp(self):
        async with ext.async_session_factory() as db:
            user = await db.get(User, self.user_id)
            user.tf_primary_method = "authenticator"
            user.tf_totp_secret = pyotp.random_base32()
            db.add(OAuth(provider="google", provider_user_id="fixture", user=user))
            await db.commit()
        client = self.app.test_client()
        await client.get("/_fixture/oauth?verified=true")
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)
        async with client.session_transaction() as cookie:
            self.assertIn("tf_user_id", cookie)
            self.assertNotIn("_user_id", cookie)

    async def test_missing_oauth_state_rejected_before_exchange(self):
        token_client = AsyncMock()
        with patch("stk.public.views.get_github_client", return_value=token_client):
            await self.app.test_client().get("/login/github/callback?code=fixture")
        token_client.fetch_token.assert_not_awaited()

    async def test_redis_login_rotates_external_sid(self):
        self.app.session_interface = RedisSessionInterface(
            redis=MemoryRedis(),
            key_prefix="session:",
            use_signer=False,
            permanent=True,
            SESSION_PROTECTION=False,
            SESSION_REVERSE_PROXY=False,
            SESSION_STATIC_FILE=False,
        )
        attacker = self.app.test_client()
        await attacker.get("/login")
        sid = next(c.value for c in attacker.cookie_jar if c.name == "session")
        victim = self.app.test_client()
        victim.set_cookie("localhost", "session", sid)
        await self.login(victim)
        self.assertNotEqual((await attacker.get("/dashboard/")).status_code, 200)
        self.assertFalse(any(c.value == sid for c in victim.cookie_jar))

    async def test_websocket_rejects_foreign_origin(self):
        client = self.app.test_client()
        await self.login(client)
        with self.assertRaises(WebsocketDisconnectError):
            async with client.websocket(
                "/ws", headers={"Origin": "https://foreign.example"}
            ) as ws:
                await ws.receive()

    async def test_websocket_closes_after_logout(self):
        self.app.config["STK_WS_AUTH_INTERVAL"] = 0.02
        client = self.app.test_client()
        await self.login(client)
        async with client.websocket(
            "/ws", headers={"Origin": "http://localhost"}
        ) as ws:
            await ws.receive()
            token = await self.csrf(client)
            await client.post("/logout", form={"csrf_token": token})
            with self.assertRaises(WebsocketDisconnectError):
                await asyncio.wait_for(ws.receive(), 1)

    async def test_admin_password_policy_cannot_be_bypassed(self):
        client = self.app.test_client()
        await self.login(client)
        token = await self.csrf(client)
        response = await client.post(
            f"/api/user/{self.user_id}",
            json={"item": {"password": "short"}},
            headers={"X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 400)

    async def test_invalid_json_mutation_is_client_error(self):
        client = self.app.test_client()
        await self.login(client)
        token = await self.csrf(client)
        response = await client.post(
            "/api/role/",
            data="garbage",
            headers={"Content-Type": "text/plain", "X-CSRFToken": token},
        )
        self.assertEqual(response.status_code, 400)

    async def test_pagination_is_bounded(self):
        client = self.app.test_client()
        await self.login(client)
        response = await client.get("/api/users?per_page=1000000&page=-1")
        self.assertEqual(response.status_code, 400)

    async def test_oauth_replay_cannot_reuse_transaction(self):
        client = self.app.test_client()
        await client.get("/login/github")
        async with client.session_transaction() as cookie:
            reference = cookie["oauth_github"]
        from quart_security import SecurityState

        async with ext.async_session_factory() as db:
            transaction = (await db.get(SecurityState, reference)).payload
        from stk.public.views import consume_oauth

        async with self.app.test_request_context(
            "/login/github/callback?code=fixture&state=" + transaction["state"]
        ):
            from quart import session

            session["oauth_github"] = reference
            self.assertIsNotNone(await consume_oauth("github"))
            session["oauth_github"] = reference
            self.assertIsNone(await consume_oauth("github"))

    async def test_auth_limits_are_shared_and_atomic(self):
        import tempfile

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from stk.utils.ratelimit import consume_limit

        with tempfile.TemporaryDirectory() as directory:
            engine = create_async_engine(f"sqlite+aiosqlite:///{directory}/limits.db")
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            if ext.engine.dialect.name == "postgresql":
                factory = ext.async_session_factory
            outcomes = await asyncio.gather(
                *(consume_limit(factory, "fixture", 3, 60) for _ in range(12))
            )
            self.assertEqual(sum(outcomes), 3)
            self.assertFalse(await consume_limit(factory, "fixture", 3, 60))
            await engine.dispose()

    @unittest.skipUnless(
        os.environ.get("STK_TEST_REDIS_URL"), "requires isolated Redis test service"
    )
    async def test_real_redis_session_rotation_and_logout(self):
        import redis.asyncio as redis

        backend = redis.from_url(os.environ["STK_TEST_REDIS_URL"])
        self.app.session_interface = RedisSessionInterface(
            redis=backend,
            key_prefix="review:" + secrets.token_hex(8) + ":",
            use_signer=False,
            permanent=True,
            SESSION_PROTECTION=False,
            SESSION_REVERSE_PROXY=False,
            SESSION_STATIC_FILE=False,
        )
        try:
            attacker = self.app.test_client()
            await attacker.get("/login")
            sid = next(
                cookie.value
                for cookie in attacker.cookie_jar
                if cookie.name == "session"
            )
            victim = self.app.test_client()
            victim.set_cookie("localhost", "session", sid)
            await self.login(victim)
            self.assertIsNone(
                await backend.get(self.app.session_interface.key_prefix + sid)
            )
            self.assertNotEqual((await attacker.get("/dashboard/")).status_code, 200)
            self.assertEqual((await victim.get("/dashboard/")).status_code, 200)
            authenticated_sid = next(
                cookie.value for cookie in victim.cookie_jar if cookie.name == "session"
            )
            copied = self.app.test_client()
            copied.set_cookie("localhost", "session", authenticated_sid)
            self.assertEqual((await copied.get("/dashboard/")).status_code, 200)
            csrf = await self.csrf(victim, "/change")
            response = await victim.post(
                "/change",
                form={
                    "password": "Password123!",
                    "new_password": "Replacement123!",
                    "new_password_confirm": "Replacement123!",
                    "csrf_token": csrf,
                },
            )
            self.assertEqual(response.status_code, 302)
            self.assertIsNone(
                await backend.get(
                    self.app.session_interface.key_prefix + authenticated_sid
                )
            )
            self.assertNotEqual((await copied.get("/dashboard/")).status_code, 200)
            token = await self.csrf(victim)
            await victim.post("/logout", form={"csrf_token": token})
            self.assertNotEqual((await victim.get("/dashboard/")).status_code, 200)
        finally:
            await backend.aclose()

    async def test_websocket_rejects_message_flood(self):
        self.app.config["STK_WS_MESSAGE_LIMIT"] = 2
        client = self.app.test_client()
        await self.login(client)
        async with client.websocket(
            "/ws", headers={"Origin": "http://localhost"}
        ) as connection:
            await connection.receive()
            for _ in range(3):
                await connection.send("ignored")
            with self.assertRaises(WebsocketDisconnectError):
                await asyncio.wait_for(connection.receive(), 1)

    async def test_google_id_token_validates_signature_and_claims(self):
        import time
        from urllib.parse import parse_qs, urlsplit

        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from joserfc import jwt
        from joserfc.jwk import RSAKey

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        private = key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        public = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self.app.config["GOOGLE_OAUTH_CLIENT_ID"] = "fixture-client"
        discovery = {
            "authorization_endpoint": "https://accounts.google.com/auth",
            "token_endpoint": "https://accounts.google.com/token",
            "jwks_uri": "https://accounts.google.com/keys",
        }
        import httpx

        for invalid in (None, "nonce", "iss", "aud", "exp", "signature"):
            with self.subTest(invalid=invalid):
                client = self.app.test_client()
                with patch(
                    "stk.public.views.google_discovery",
                    new=AsyncMock(return_value=discovery),
                ):
                    start = await client.get("/login/google")
                args = parse_qs(urlsplit(start.location).query)
                self.assertEqual(args["code_challenge_method"], ["S256"])
                claims = {
                    "iss": "https://accounts.google.com",
                    "sub": "new-fixture",
                    "aud": "fixture-client",
                    "exp": int(time.time()) + 300,
                    "iat": int(time.time()),
                    "nonce": args["nonce"][0],
                    "email": "new@example.com",
                    "email_verified": True,
                }
                if invalid in {"nonce", "iss", "aud"}:
                    claims[invalid] = "wrong"
                if invalid == "exp":
                    claims["exp"] = int(time.time()) - 300
                signing_key = private
                if invalid == "signature":
                    signing_key = rsa.generate_private_key(
                        public_exponent=65537, key_size=2048
                    ).private_bytes(
                        serialization.Encoding.PEM,
                        serialization.PrivateFormat.PKCS8,
                        serialization.NoEncryption(),
                    )
                encoded = jwt.encode(
                    {"alg": "RS256"}, claims, RSAKey.import_key(signing_key)
                )
                oauth = AsyncMock()
                oauth.__aenter__.return_value = oauth
                oauth.fetch_token.return_value = {
                    "id_token": encoded,
                    "access_token": "fixture",
                }
                response = httpx.Response(
                    200, request=httpx.Request("GET", discovery["jwks_uri"]), json={}
                )
                response.json = lambda: {"keys": [RSAKey.import_key(public).as_dict()]}
                http = AsyncMock()
                http.__aenter__.return_value = http
                http.get.return_value = response
                with (
                    patch(
                        "stk.public.views.google_discovery",
                        new=AsyncMock(return_value=discovery),
                    ),
                    patch("stk.public.views.get_google_client", return_value=oauth),
                    patch("stk.public.views.httpx.AsyncClient", return_value=http),
                ):
                    await client.get(
                        "/login/google/callback?code=fixture&state=" + args["state"][0]
                    )
                oauth.fetch_token.assert_awaited_once()
                self.assertIn("code_verifier", oauth.fetch_token.call_args.kwargs)
                status = (await client.get("/dashboard/")).status_code
                self.assertEqual(status == 200, invalid is None)

    async def test_websocket_closes_when_auth_state_changes(self):
        from quart_security import SecurityState

        for reason in ("inactive", "expired", "password"):
            with self.subTest(reason=reason):
                self.app.config["STK_WS_AUTH_INTERVAL"] = 0.02
                client = self.app.test_client()
                await self.login(client)
                async with client.session_transaction() as cookie:
                    auth_token = cookie["_id"]
                async with client.websocket(
                    "/ws", headers={"Origin": "http://localhost"}
                ) as connection:
                    await connection.receive()
                    if reason == "password":
                        csrf = await self.csrf(client, "/change")
                        response = await client.post(
                            "/change",
                            form={
                                "password": "Password123!",
                                "new_password": "Replacement123!",
                                "new_password_confirm": "Replacement123!",
                                "csrf_token": csrf,
                            },
                        )
                        self.assertEqual(response.status_code, 302)
                    else:
                        async with ext.async_session_factory() as db:
                            if reason == "inactive":
                                user = await db.get(User, self.admin_id)
                                user.active = False
                            else:
                                state = await db.get(SecurityState, auth_token)
                                state.expires_at = 0
                            await db.commit()
                    with self.assertRaises(WebsocketDisconnectError):
                        await asyncio.wait_for(connection.receive(), 1)
                async with ext.async_session_factory() as db:
                    user = await db.get(User, self.admin_id)
                    user.active = True
                    user.password = hash_password("Password123!", app=self.app)
                    await db.commit()

    async def test_broadcast_is_targeted_and_queue_is_bounded(self):
        from stk.websocket import _clients, broadcast

        target, unrelated = asyncio.Queue(maxsize=2), asyncio.Queue(maxsize=2)
        _clients["fixture-target"] = {target}
        _clients["fixture-other"] = {unrelated}
        try:
            for _ in range(3):
                await broadcast({"type": "notification"}, "fixture-target")
            self.assertTrue(unrelated.empty())
            self.assertEqual(target.qsize(), 1)
            self.assertIsNone(target.get_nowait())
        finally:
            del _clients["fixture-target"]
            del _clients["fixture-other"]

    async def test_activity_does_not_broadcast_uncommitted_data(self):
        from quart import g

        from stk.user.models import Activity
        from stk.websocket import _clients

        queue = asyncio.Queue()
        _clients["fixture-observer"] = {queue}
        try:
            async with self.app.test_request_context("/"):
                async with ext.async_session_factory() as db:
                    g.db_session = db
                    await Activity.register(self.admin_id, "private audit event")
                    await db.rollback()
            self.assertTrue(queue.empty())
        finally:
            del _clients["fixture-observer"]

    async def test_invalid_host_rejected_before_authentication(self):
        self.app.config["STK_PUBLIC_URL"] = "https://app.example.com"
        response = await self.app.test_client().get(
            "/login", headers={"Host": "attacker.example"}
        )
        self.assertEqual(response.status_code, 400)

    async def test_json_csrf_token_preserves_passkey_api_contract(self):
        client = self.app.test_client()
        await self.login(client)
        csrf = await self.csrf(client)
        response = await client.post(
            "/wan-delete", json={"name": "missing", "csrf_token": csrf}
        )
        self.assertEqual(response.status_code, 404)
        response = await client.post(
            "/wan-delete", json={"name": "missing", "csrf_token": [csrf]}
        )
        self.assertEqual(response.status_code, 400)

    async def test_shared_auth_quota_covers_oauth_and_allows_logout(self):
        client = self.app.test_client()
        await self.login(client)
        csrf = await self.csrf(client)
        self.app.config.update(
            QUART_RATE_LIMITER_ENABLED=True, STK_AUTH_ATTEMPT_LIMIT=1
        )
        self.assertEqual(
            (await client.get("/login/google/callback?code=fixture")).status_code, 302
        )
        token_client = AsyncMock()
        with patch("stk.public.views.get_github_client", return_value=token_client):
            response = await client.get("/login/github/callback?code=fixture")
        self.assertEqual(response.status_code, 429)
        token_client.fetch_token.assert_not_awaited()
        response = await client.post("/logout", form={"csrf_token": csrf})
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)

    async def test_linked_oauth_respects_lockout_and_deactivation(self):
        from datetime import UTC, datetime, timedelta

        async with ext.async_session_factory() as db:
            user = await db.get(User, self.user_id)
            user.locked_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(
                minutes=1
            )
            db.add(OAuth(provider="google", provider_user_id="fixture", user=user))
            await db.commit()
        client = self.app.test_client()
        await client.get("/_fixture/oauth?verified=true")
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)
        async with ext.async_session_factory() as db:
            user = await db.get(User, self.user_id)
            user.locked_until = None
            user.active = False
            await db.commit()
        await client.get("/_fixture/oauth?verified=true")
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)

    async def test_admin_password_policy_runs_after_authorization(self):
        client = self.app.test_client()
        csrf = await self.csrf(client)
        self.app.config["SECURITY_PASSWORD_BREACH_CHECK"] = True
        checker = AsyncMock(return_value=False)
        with patch("stk.security.password_is_breached", new=checker):
            response = await client.post(
                f"/api/user/{self.user_id}",
                json={"item": {"password": "UnbreachedLongPassword123!"}},
                headers={"X-CSRFToken": csrf},
            )
        self.assertEqual(response.status_code, 401)
        checker.assert_not_awaited()
