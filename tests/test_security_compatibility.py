"""Exercise stk's authentication integration with quart-security 2."""

import unittest

import pyotp
from quart import g
from quart_security import hash_password
from sqlalchemy import select

import stk.extensions as ext
from stk.app import create_app
from stk.settings import Config
from stk.user.models import Base, SecurityState, Session, User


class SecurityConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///:memory:"
    SESSION_TYPE = None
    SECURITY_COOKIE_SECURE = False
    SECURITY_PASSWORD_SALT = "test-salt"
    QUART_RATE_LIMITER_ENABLED = False


class SecurityCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app(SecurityConfig)
        async with ext.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            user = User(
                email="user@example.com",
                password=hash_password("TestPassword123!", app=self.app),
                active=True,
            )
            db.add(user)
            await db.commit()
            self.user_id = user.id

    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def login(self, client):
        response = await client.get("/login")
        self.assertEqual(response.status_code, 200)
        async with client.session_transaction() as cookie:
            csrf = cookie["_csrf_token"]
        response = await client.post(
            "/login",
            form={
                "email": "user@example.com",
                "password": "TestPassword123!",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(response.status_code, 302)
        async with client.session_transaction() as cookie:
            return dict(cookie)

    async def test_startup_validates_state_table_without_request(self):
        async with self.app.test_app():
            pass

    async def test_logout_rejects_copied_cookie(self):
        client = self.app.test_client()
        saved = await self.login(client)
        self.assertEqual((await client.get("/dashboard/")).status_code, 200)
        await client.get("/login")
        async with client.session_transaction() as cookie:
            csrf = cookie["_csrf_token"]
        response = await client.post("/logout", form={"csrf_token": csrf})
        self.assertEqual(response.status_code, 302)
        async with client.session_transaction() as cookie:
            cookie.clear()
            cookie.update(saved)
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)

    async def test_single_session_revokes_previous_authentication(self):
        self.app.config["DISABLE_MULTIPLE_SESSIONS"] = True
        first = self.app.test_client()
        saved = await self.login(first)
        await self.login(self.app.test_client())
        self.assertNotEqual((await first.get("/dashboard/")).status_code, 200)
        async with ext.async_session_factory() as db:
            self.assertIsNone(await db.get(SecurityState, saved["_id"]))
            tracked = await db.scalar(
                select(Session).where(Session.session_token == saved["_id"])
            )
            self.assertFalse(tracked.is_active)

    async def test_admin_model_password_update_revokes_cookie(self):
        client = self.app.test_client()
        await self.login(client)
        async with self.app.test_request_context("/"):
            async with ext.async_session_factory() as db:
                g.db_session = db
                user = await db.get(User, self.user_id)
                await user.from_dict({"password": "Replacement123!"})
                await db.commit()
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)

    async def test_totp_required_and_code_cannot_be_reused(self):
        secret = pyotp.random_base32()
        async with ext.async_session_factory() as db:
            user = await db.get(User, self.user_id)
            user.tf_primary_method = "authenticator"
            user.tf_totp_secret = secret
            await db.commit()
        client = self.app.test_client()
        pending = await self.login(client)
        self.assertNotIn("_user_id", pending)
        self.assertNotEqual((await client.get("/dashboard/")).status_code, 200)
        code = pyotp.TOTP(secret).now()
        response = await client.post(
            "/tf-validate", form={"code": code, "csrf_token": pending["_csrf_token"]}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual((await client.get("/dashboard/")).status_code, 200)
        second = self.app.test_client()
        pending = await self.login(second)
        await second.post(
            "/tf-validate", form={"code": code, "csrf_token": pending["_csrf_token"]}
        )
        self.assertNotEqual((await second.get("/dashboard/")).status_code, 200)

    def test_cookie_setting_preserves_local_http_support(self):
        self.assertFalse(self.app.config["SESSION_COOKIE_SECURE"])
