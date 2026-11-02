import asyncio
import json
import unittest

from quart_security import hash_password

import stk.extensions as ext
import stk.notification
from stk.app import Stk
from stk.extensions import Base
from stk.notification import notify
from stk.settings import TestingConfig
from stk.user.models import User


class NotificationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Stk(__name__, config=TestingConfig, extensions=[stk.notification])
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

    async def test_socket_opened_later_does_not_replay_earlier_pushes(self):
        alice, bob = (
            await self.client("alice@example.com"),
            await self.client("bob@example.com"),
        )
        origin = {"Origin": "http://localhost"}
        async with alice.websocket("/ws", headers=origin) as alice_ws:
            await alice_ws.receive()
            await notify(self.bob, "Before Bob connected")
            await asyncio.sleep(0.5)  # the running poller has passed it
            async with bob.websocket("/ws", headers=origin) as bob_ws:
                await bob_ws.receive()
                with self.assertRaises(TimeoutError):
                    await asyncio.wait_for(bob_ws.receive(), 0.6)

    async def test_push_from_another_process_reaches_the_socket(self):
        """`stk worker` and other uvicorn workers are separate processes."""
        import sys
        import tempfile
        from pathlib import Path

        await ext.engine.dispose()
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        uri = f"sqlite+aiosqlite:///{Path(folder.name) / 'shared.db'}"
        config = type(
            "SharedConfig", (TestingConfig,), {"SQLALCHEMY_DATABASE_URI": uri}
        )
        self.app = Stk(__name__, config=config, extensions=[stk.notification])
        async with ext.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            user = User(
                email="carol@example.com",
                active=True,
                password=hash_password("Password123!", app=self.app),
            )
            db.add(user)
            await db.commit()
        carol = await self.client("carol@example.com")
        script = (
            "import asyncio, sys\n"
            "from stk.app import Stk\n"
            "from stk.settings import TestingConfig\n"
            "from stk.websocket import broadcast\n"
            "C = type('C', (TestingConfig,), {'SQLALCHEMY_DATABASE_URI': sys.argv[1]})\n"
            "Stk('other', config=C)\n"
            "asyncio.run(broadcast({'type': 'progress', 'done': 40}, int(sys.argv[2])))\n"
        )
        async with carol.websocket("/ws", headers={"Origin": "http://localhost"}) as ws:
            await ws.receive()
            other = await asyncio.create_subprocess_exec(
                sys.executable, "-c", script, uri, str(user.id)
            )
            self.assertEqual(await other.wait(), 0)
            message = json.loads(await asyncio.wait_for(ws.receive(), 2))
        self.assertEqual(message, {"type": "progress", "done": 40})



class CoreModelNameTest(unittest.TestCase):
    def test_app_model_named_message_resolves_by_string(self):
        """relationship("Message") looks the name up across the shared Base."""
        import subprocess
        import sys

        script = (
            "from sqlalchemy import Column, ForeignKey, Integer\n"
            "from sqlalchemy.orm import configure_mappers, relationship\n"
            "import stk.websocket\n"
            "from stk.extensions import Base\n"
            "class Message(Base):\n"
            "    __tablename__ = 'app_message'\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    parent_id = Column(Integer, ForeignKey('app_message.id'))\n"
            "    replies = relationship('Message', lazy='selectin')\n"
            "configure_mappers()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])

if __name__ == "__main__":
    unittest.main()
