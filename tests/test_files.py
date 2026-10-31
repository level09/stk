"""Uploads: bytes stored once, types sniffed, downloads checked and safe."""

import io
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from quart import current_app
from quart.datastructures import FileStorage
from quart_security import hash_password

import stk.extensions as ext
import stk.files
from stk.app import Stk
from stk.files import store
from stk.settings import TestingConfig
from stk.user.models import Base, Role, User

PDF = b"%PDF-1.4\n%fake but signed\n"


def png(color="red"):
    out = io.BytesIO()
    Image.new("RGB", (800, 600), color).save(out, "PNG")
    return out.getvalue()


class FilesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.dir = tempfile.TemporaryDirectory()

        class Config(TestingConfig):
            SECURITY_PASSWORD_SALT = "test-salt"
            STK_UPLOAD_DIR = self.dir.name
            STK_UPLOAD_MAX_BYTES = 100_000

        self.app = Stk(__name__, config=Config, extensions=[stk.files])
        async with ext.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            admin = User(email="admin@example.com", active=True)
            admin.roles.append(Role(name="admin"))
            users = [
                admin,
                User(email="alice@example.com", active=True),
                User(email="bob@example.com", active=True),
            ]
            for user in users:
                user.password = hash_password("Password123!", app=self.app)
            db.add_all(users)
            await db.commit()

    async def asyncTearDown(self):
        await ext.engine.dispose()
        self.dir.cleanup()

    async def client(self, email="alice@example.com"):
        client = self.app.test_client()
        await client.get("/login")
        async with client.session_transaction() as cookie:
            token = cookie["_csrf_token"]
        response = await client.post(
            "/login",
            form={"email": email, "password": "Password123!", "csrf_token": token},
        )
        self.assertEqual(response.status_code, 302)
        # Login rotates the session, and its token with it.
        await client.get("/dashboard/")
        async with client.session_transaction() as cookie:
            client.token = cookie["_csrf_token"]
        return client

    async def upload(self, client, data, name="photo.png", claimed="image/png"):
        part = FileStorage(io.BytesIO(data), filename=name, content_type=claimed)
        return await client.post(
            "/files/",
            files={"file": part},
            headers={"X-CSRFToken": client.token, "Accept": "application/json"},
        )

    def stored(self):
        return sorted(p.name for p in Path(self.dir.name).rglob("*") if p.is_file())

    async def test_same_bytes_are_stored_once(self):
        alice, bob = await self.client(), await self.client("bob@example.com")
        data = png()
        first = (await (await self.upload(alice, data)).get_json())["item"]
        again = (await (await self.upload(alice, data, "copy.png")).get_json())["item"]
        other = (await (await self.upload(bob, data)).get_json())["item"]
        self.assertEqual(first["id"], again["id"])
        self.assertNotEqual(first["id"], other["id"])
        self.assertEqual(first["sha256"], other["sha256"])
        # The image and its thumbnail, once each.
        self.assertEqual(len(self.stored()), 2)

    async def test_size_limit(self):
        client = await self.client()
        # Just over the file limit, then far over it, where the body read stops.
        for padding in (100_000, 1_000_000):
            response = await self.upload(client, PDF + b"0" * padding)
            self.assertEqual(response.status_code, 413)
        self.assertEqual(self.stored(), [])

    async def test_unknown_type_is_refused(self):
        client = await self.client()
        response = await self.upload(client, b"<svg onload=alert(1)>", "x.svg")
        self.assertEqual(response.status_code, 415)
        self.assertEqual(self.stored(), [])

    async def test_sniffed_type_beats_the_client(self):
        client = await self.client()
        response = await self.upload(client, PDF, "../../evil.png", "image/png")
        item = (await response.get_json())["item"]
        self.assertEqual(item["content_type"], "application/pdf")
        self.assertEqual(item["filename"], "evil.png")
        self.assertIsNone(item["thumb_url"])
        download = await client.get(item["url"])
        self.assertEqual(download.content_type, "application/pdf")
        self.assertTrue(
            download.headers["Content-Disposition"].startswith("attachment")
        )
        self.assertEqual(download.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(await download.get_data(), PDF)

    async def test_image_is_inline_with_a_thumbnail(self):
        client = await self.client()
        item = (await (await self.upload(client, png())).get_json())["item"]
        download = await client.get(item["url"])
        self.assertEqual(download.content_type, "image/png")
        self.assertNotIn("Content-Disposition", download.headers)
        thumb = await client.get(item["thumb_url"])
        with Image.open(io.BytesIO(await thumb.get_data())) as image:
            self.assertEqual((image.format, image.size), ("WEBP", (480, 360)))

    async def test_undecodable_image_is_refused(self):
        response = await self.upload(await self.client(), png()[:60])
        self.assertEqual(response.status_code, 400)

    async def test_access_is_uploader_or_admin(self):
        alice = await self.client()
        url = (await (await self.upload(alice, PDF)).get_json())["item"]["url"]
        bob = await self.client("bob@example.com")
        admin = await self.client("admin@example.com")
        self.assertEqual((await alice.get(url)).status_code, 200)
        self.assertEqual((await bob.get(url)).status_code, 404)
        self.assertEqual((await admin.get(url)).status_code, 200)
        anonymous = await self.app.test_client().get(url)
        self.assertNotEqual(anonymous.status_code, 200)

    async def test_app_overrides_access(self):
        async def everyone(user, file):
            return True

        self.app.file_access = everyone
        alice = await self.client()
        url = (await (await self.upload(alice, PDF)).get_json())["item"]["url"]
        bob = await self.client("bob@example.com")
        self.assertEqual((await bob.get(url)).status_code, 200)

    async def test_upload_requires_csrf(self):
        client = await self.client()
        client.token = "wrong"
        self.assertEqual((await self.upload(client, PDF)).status_code, 400)

    async def test_keys_cannot_traverse(self):
        async with self.app.app_context():
            for key in ("../../etc/passwd", "a" * 63 + "/", "A" * 64, ""):
                with self.assertRaises(ValueError):
                    store.path(key)
            sha256 = store.save(b"bytes")
            self.assertTrue(store.exists(sha256))
            with store.open(sha256) as f:
                self.assertEqual(f.read(), b"bytes")
            store.delete(sha256)
            self.assertFalse(store.exists(sha256))
            root = Path(current_app.config["STK_UPLOAD_DIR"])
            self.assertTrue(store.path(sha256).is_relative_to(root))

    def test_unsniffable_allowed_type_fails_at_startup(self):
        class Config(TestingConfig):
            SECURITY_PASSWORD_SALT = "test-salt"
            STK_UPLOAD_TYPES = ("text/html",)

        with self.assertRaises(ValueError):
            Stk(__name__, config=Config, extensions=[stk.files])


if __name__ == "__main__":
    unittest.main()
