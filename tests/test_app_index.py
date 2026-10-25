"""An app may replace stk's landing page, and verify judges where / lands."""

import unittest
from types import SimpleNamespace

from quart import redirect

from stk.app import Stk
from stk.checks import check_http_index
from stk.cli.main import _app_sections
from stk.settings import TestingConfig


class AppIndexTest(unittest.IsolatedAsyncioTestCase):
    async def test_index_can_be_replaced_and_a_redirect_passes_the_check(self):
        app = Stk(__name__, config=TestingConfig)

        async def home():
            return redirect("/login")

        app.view_functions["public.index"] = home
        response = await app.test_client().get("/")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(await check_http_index(app))

    async def test_a_redirect_to_a_broken_page_fails_the_check(self):
        app = Stk(__name__, config=TestingConfig)

        async def home():
            return redirect("/nowhere")

        app.view_functions["public.index"] = home
        self.assertFalse(await check_http_index(app))


class AppHelpSectionsTest(unittest.TestCase):
    def test_app_sections_come_from_config(self):
        app = Stk(__name__, config=TestingConfig)
        app.config["STK_CLI_SECTIONS"] = [("Runs", ("worker", "enrich"))]
        ctx = SimpleNamespace(
            ensure_object=lambda _: SimpleNamespace(load_app=lambda: app)
        )
        self.assertEqual(_app_sections(ctx), [("Runs", ["worker", "enrich"])])
