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
