"""Unhandled errors render as 500 even when the exception has its own .code."""

import unittest

from sqlalchemy.exc import OperationalError

from stk.app import Stk
from stk.settings import TestingConfig


class ErrorHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_database_error_is_500_and_logged(self):
        app = Stk(__name__, config=TestingConfig)

        @app.get("/boom")
        async def boom():
            raise OperationalError("SELECT 1", {}, Exception("no such table"))

        with self.assertLogs("stk.app", level="ERROR"):
            response = await app.test_client().get("/boom")
        self.assertEqual(response.status_code, 500)

    async def test_error_pages_mount_the_layout(self):
        # 405 has no template of its own: error.html names it, not "500".
        client = Stk(__name__, config=TestingConfig).test_client()
        for path, code, text in (
            ("/missing", 404, "that page doesn't exist"),
            ("/logout", 405, "The method is not allowed"),
        ):
            response = await client.get(path)
            self.assertEqual(response.status_code, code)
            page = await response.get_data(as_text=True)
            self.assertIn('id="app" v-cloak', page)
            self.assertIn(".mount('#app')", page)
            self.assertIn(f">{code}</h1>", page)
            self.assertIn(text, page)
            self.assertNotIn("something went wrong", page)
