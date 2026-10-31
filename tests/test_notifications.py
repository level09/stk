import asyncio
import json
import unittest

from quart_security import hash_password

import stk.extensions as ext
from stk.app import Stk
from stk.extensions import Base
from stk.notification import notify
from stk.settings import TestingConfig
from stk.user.models import User


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Stk(__name__, config=TestingConfig)
        async with ext.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            users = [
                User(
                    email=email,
                    active=True,
                    password=hash_password("Password123!", app=self.app),
                )
                for email in ("alice@example.com", "bob@example.com")
            ]
            db.add_all(users)
            await db.commit()
            self.alice, self.bob = (u.id for u in users)

    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def client(self, email):
        client = self.app.test_client()
        await client.get("/login")
        async with client.session_transaction() as cookie:
            token = cookie["_csrf_token"]
        response = await client.post(
            "/login",
            form={"email": email, "password": "Password123!", "csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        # Login rotates the CSRF token.
        await client.get("/login")
        async with client.session_transaction() as cookie:
            client.headers = {"X-CSRFToken": cookie["_csrf_token"]}
        return client

    async def test_list_unread_and_mark_read(self):
        first = await notify(self.alice, "Export ready", link="/exports/1")
        await notify(self.alice, "Invoice paid", kind="billing", body="#42")
        alice = await self.client("alice@example.com")

        listing = await (await alice.get("/api/notifications")).get_json()
        self.assertEqual(listing["total"], 2)
        self.assertEqual(listing["perPage"], 20)
        self.assertEqual(
            [n["title"] for n in listing["items"]], ["Invoice paid", "Export ready"]
        )
        self.assertEqual(listing["items"][0]["kind"], "billing")
        page = await (
            await alice.get("/api/notifications?per_page=1&page=2")
        ).get_json()
        self.assertEqual([n["id"] for n in page["items"]], [first.id])

        unread = "/api/notifications/unread"
        self.assertEqual((await (await alice.get(unread)).get_json())["count"], 2)
        response = await alice.post(
            f"/api/notifications/{first.id}/read", json={}, headers=alice.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await (await alice.get(unread)).get_json())["count"], 1)
        await alice.post("/api/notifications/read", json={}, headers=alice.headers)
        self.assertEqual((await (await alice.get(unread)).get_json())["count"], 0)

    async def test_users_see_only_their_own(self):
        theirs = await notify(self.alice, "For Alice")
        bob = await self.client("bob@example.com")
        listing = await (await bob.get("/api/notifications")).get_json()
        self.assertEqual((listing["items"], listing["total"]), ([], 0))
        response = await bob.post(
            f"/api/notifications/{theirs.id}/read", json={}, headers=bob.headers
        )
        self.assertEqual(response.status_code, 404)
        await bob.post("/api/notifications/read", json={}, headers=bob.headers)
        alice = await self.client("alice@example.com")
        count = await (await alice.get("/api/notifications/unread")).get_json()
        self.assertEqual(count["count"], 1)

    async def test_endpoints_require_login(self):
        client = self.app.test_client()
        for path in ("/api/notifications", "/api/notifications/unread"):
            self.assertEqual((await client.get(path)).status_code, 302)

    async def test_link_must_be_same_origin(self):
        for link in (
            "javascript:alert(1)",
            "https://evil.example",
            "//evil.example",
            "/\t/evil.example",
            "/\n/evil.example",
        ):
            with self.assertRaises(ValueError):
                await notify(self.alice, "Bad", link=link)

    async def test_push_reaches_only_the_recipient(self):
        alice, bob = (
            await self.client("alice@example.com"),
            await self.client("bob@example.com"),
        )
        origin = {"Origin": "http://localhost"}
        async with (
            alice.websocket("/ws", headers=origin) as alice_ws,
            bob.websocket("/ws", headers=origin) as bob_ws,
        ):
            await alice_ws.receive()
            await bob_ws.receive()
            row = await notify(self.alice, "Live", link="/dashboard")
            message = json.loads(await asyncio.wait_for(alice_ws.receive(), 1))
            self.assertEqual(
                (message["type"], message["id"], message["title"]),
                ("notification", row.id, "Live"),
            )
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(bob_ws.receive(), 0.2)


if __name__ == "__main__":
    unittest.main()
