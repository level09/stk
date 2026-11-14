"""An app may replace stk's landing page, and verify judges where / lands."""

import contextlib
import io
import sys
import tempfile
import unittest
from types import ModuleType, SimpleNamespace

from quart import Blueprint, redirect

from stk import checks
from stk.app import Stk
from stk.checks import check_http_index, check_unique_routes
from stk.cli.main import _app_sections
from stk.settings import TestingConfig


class AppIndexTest(unittest.IsolatedAsyncioTestCase):
    async def test_an_extension_route_for_slash_replaces_the_landing_page(self):
        home = Blueprint("home", __name__)

        @home.get("/")
        async def own_home():
            return "own home"

        module = ModuleType("own_home_ext")
        module.init_app = lambda app: app.register_blueprint(home)
        with tempfile.TemporaryDirectory() as path:
            module.__path__ = [path]
            sys.modules[module.__name__] = module
            try:
                app = Stk(__name__, config=TestingConfig, extensions=[module])
            finally:
                del sys.modules[module.__name__]
        response = await app.test_client().get("/")
        self.assertEqual(await response.get_data(as_text=True), "own home")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(await check_unique_routes(app))

    async def test_index_can_be_replaced_and_a_redirect_passes_the_check(self):
        app = Stk(__name__, config=TestingConfig)

        async def home():
            return redirect("/login")

        app.view_functions["public.index"] = home
        response = await app.test_client().get("/")
        self.assertEqual(response.status_code, 302)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(await check_http_index(app))

    async def test_a_redirect_to_a_broken_page_fails_the_check(self):
        app = Stk(__name__, config=TestingConfig)

        async def home():
            return redirect("/nowhere")

        app.view_functions["public.index"] = home
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertFalse(await check_http_index(app))
        self.assertIn("Expected 200, got 404", out.getvalue())
        self.assertEqual(checks.RESULTS[-1]["detail"], "Expected 200, got 404")


class AppHelpSectionsTest(unittest.TestCase):
    def test_app_sections_come_from_config(self):
        app = Stk(__name__, config=TestingConfig)
        app.config["STK_CLI_SECTIONS"] = [("Runs", ("worker", "enrich"))]
        ctx = SimpleNamespace(
            ensure_object=lambda _: SimpleNamespace(load_app=lambda: app)
        )
        self.assertEqual(_app_sections(ctx), [("Runs", ["worker", "enrich"])])
