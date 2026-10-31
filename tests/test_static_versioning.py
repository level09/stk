"""Static URLs carry a content hash, and only versioned responses cache forever."""

import unittest

from quart import url_for

from stk.app import Stk
from stk.settings import TestingConfig


class StaticVersioningTests(unittest.IsolatedAsyncioTestCase):
    async def test_versioned_static_is_immutable_and_bare_static_revalidates(self):
        app = Stk(__name__, config=TestingConfig)
        async with app.test_request_context("/"):
            url = url_for("static", filename="js/config.js")
        self.assertRegex(url, r"^/static/js/config\.js\?v=[0-9a-f]{12}$")

        client = app.test_client()
        versioned = await client.get(url)
        self.assertEqual(versioned.status_code, 200)
        self.assertIn("immutable", versioned.headers["Cache-Control"])
        bare = await client.get("/static/js/config.js")
        self.assertEqual(bare.headers["Cache-Control"], "no-cache")

    async def test_errors_and_session_cookies_are_never_cached_publicly(self):
        app = Stk(__name__, config=TestingConfig)
        client = app.test_client()
        missing = await client.get("/static/missing.css?v=1")
        self.assertEqual(missing.status_code, 404)
        self.assertNotIn("public", missing.headers["Cache-Control"])
        # A stale login is cleared on any request, static ones included; that
        # response carries a cookie change and must stay private.
        async with client.session_transaction() as cookie:
            cookie["_user_id"] = "gone"
        async with app.test_request_context("/"):
            url = url_for("static", filename="js/config.js")
        cleared = await client.get(url)
        self.assertEqual(cleared.headers["Cache-Control"], "private, no-store")


if __name__ == "__main__":
    unittest.main()
