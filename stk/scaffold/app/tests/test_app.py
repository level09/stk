import unittest

import stk

from __app__.app import extensions
from __app__.settings import Config


class TestConfig(stk.TestingConfig, Config):
    pass


class AppTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = stk.Stk("__app__.app", config=TestConfig, extensions=extensions)

    async def test_home_page_renders(self):
        response = await self.app.test_client().get("/")
        self.assertEqual(response.status_code, 200)

    async def test_dashboard_requires_login(self):
        response = await self.app.test_client().get("/dashboard/")
        self.assertIn(response.status_code, (302, 401))
