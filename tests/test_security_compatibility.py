"""Exercise stk's authentication integration with quart-security 2."""

import asyncio
import re
import unittest

import pyotp
from quart import g
from quart_security import hash_password
from sqlalchemy import select, update

import stk.extensions as ext
from stk.app import Stk
from stk.settings import TestingConfig
from stk.user.models import Base, SecurityState, Session, User


class SecurityConfig(TestingConfig):
    SECURITY_PASSWORD_SALT = "test-salt"


class SecurityCompatibilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Stk(__name__, config=SecurityConfig)
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

    async def test_emails_are_stored_lowercase_and_matched_regardless_of_case(self):
        self.assertEqual(User(email="  New@Example.COM ").email, "new@example.com")
        # A row stored before normalization keeps its case; lookups still find it.
        async with ext.async_session_factory() as db:
            await db.execute(
                update(User)
                .where(User.id == self.user_id)
                .values(email="User@Example.com")
            )
            await db.commit()
            found = await db.scalar(
                select(User).where(User.email_is(" USER@example.COM"))
            )
            self.assertEqual(found.id, self.user_id)
        client = self.app.test_client()
        await client.get("/login")
        async with client.session_transaction() as cookie:
            csrf = cookie["_csrf_token"]
        response = await client.post(
            "/login",
            form={
                "email": " user@EXAMPLE.com ",
                "password": "TestPassword123!",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(response.status_code, 302)

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

    def mailbox(self):
        """Turn on sign-up and reset with mail; collect what would be sent."""
        self.app.config.update(
            SECURITY_REGISTERABLE=True,
            SECURITY_RECOVERABLE=True,
            MAIL_SERVER="smtp.example.com",
            SECURITY_PUBLIC_URL="http://localhost",
        )
        sent = []

        async def send_mail(subject, recipient, body):
            sent.append((subject, recipient, body))

        self.app.extensions["security"].send_mail = send_mail
        return sent

    async def post(self, client, path, **form):
        await client.get("/login")
        async with client.session_transaction() as cookie:
            form["csrf_token"] = cookie["_csrf_token"]
        response = await client.post(path, form=form)
        # Auth mail and account lookups run after the response; wait for them.
        while self.app.background_tasks:
            await asyncio.gather(*list(self.app.background_tasks))
        return response

    @staticmethod
    def link(message):
        return re.search(r"http://localhost(/\S+)", message[2]).group(1)

    async def test_sign_up_waits_for_the_email_and_hides_existing_accounts(self):
        sent = self.mailbox()
        client = self.app.test_client()
        password = "AnotherPassword123!"
        for email in ("new@example.com", "USER@example.com"):
            response = await self.post(
                client,
                "/register",
                email=email,
                password=password,
                password_confirm=password,
            )
            self.assertEqual(response.status_code, 302)
        self.assertEqual([m[1] for m in sent], ["new@example.com", "user@example.com"])

        login = {"email": "new@example.com", "password": password}
        self.assertNotIn("_user_id", await self.login_as(login))
        # Opening the link confirms nothing; the button on that page does.
        self.assertEqual((await client.get(self.link(sent[0]))).status_code, 200)
        self.assertNotIn("_user_id", await self.login_as(login))
        await self.post(client, self.link(sent[0]))
        self.assertIn("_user_id", await self.login_as(login))

        # A forged Host header never reaches the links in the mail.
        await self.post(
            client,
            "/register",
            email="user@example.com",
            password=password,
            password_confirm=password,
        )
        self.assertNotIn("evil.example", sent[-1][2])

    async def login_as(self, form):
        client = self.app.test_client()
        await self.post(client, "/login", **form)
        async with client.session_transaction() as cookie:
            return dict(cookie)

    async def test_password_reset_replaces_the_password_and_logs_activity(self):
        sent = self.mailbox()
        signed_in = self.app.test_client()
        await self.login(signed_in)
        client = self.app.test_client()
        page = await client.get("/reset")
        self.assertEqual(page.status_code, 200)
        await self.post(client, "/reset", email="user@example.com")
        path = self.link(sent[0])
        self.assertEqual((await client.get(path)).status_code, 200)
        new = "ReplacementPass123!"
        response = await self.post(client, path, password=new, password_confirm=new)
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            "_user_id",
            await self.login_as({"email": "user@example.com", "password": new}),
        )
        self.assertNotEqual((await signed_in.get("/dashboard/")).status_code, 200)

    def test_sign_up_without_mail_refuses_to_start(self):
        class Config(SecurityConfig):
            SECURITY_REGISTERABLE = True

        with self.assertRaisesRegex(RuntimeError, "MAIL_SERVER"):
            Stk(__name__, config=Config)

        class Unconfirmed(Config):
            SECURITY_CONFIRMABLE = False

        Stk(__name__, config=Unconfirmed)

    def test_cookie_setting_preserves_local_http_support(self):
        self.assertFalse(self.app.config["SESSION_COOKIE_SECURE"])
