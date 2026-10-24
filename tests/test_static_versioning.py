"""Static URLs carry a content hash, and only versioned responses cache forever."""

import unittest

from quart import url_for

from stk.app import create_app
from stk.settings import TestingConfig


class StaticVersioningTests(unittest.IsolatedAsyncioTestCase):
    async def test_versioned_static_is_immutable_and_bare_static_revalidates(self):
        app = create_app(TestingConfig)
        async with app.test_request_context("/"):
            url = url_for("static", filename="js/config.js")
        self.assertRegex(url, r"^/static/js/config\.js\?v=[0-9a-f]{12}$")

        client = app.test_client()
        versioned = await client.get(url)
        self.assertEqual(versioned.status_code, 200)
        self.assertIn("immutable", versioned.headers["Cache-Control"])
        bare = await client.get("/static/js/config.js")
        self.assertEqual(bare.headers["Cache-Control"], "no-cache")


if __name__ == "__main__":
    unittest.main()
