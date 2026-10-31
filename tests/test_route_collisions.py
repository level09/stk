"""An app route that repeats a core one is never reached; verify must say so."""

import contextlib
import io
import unittest

from quart import Blueprint

import stk.notification
from stk import checks
from stk.app import Stk
from stk.checks import check_unique_routes
from stk.settings import TestingConfig


class RouteCollisionTest(unittest.IsolatedAsyncioTestCase):
    async def test_core_routes_are_unique(self):
        app = Stk(__name__, config=TestingConfig, extensions=[stk.notification])
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(await check_unique_routes(app))

    async def test_an_app_route_shadowed_by_a_core_route_fails(self):
        app = Stk(__name__, config=TestingConfig, extensions=[stk.notification])
        inbox = Blueprint("inbox", __name__)

        @inbox.get("/api/notifications")
        async def own_notifications():
            return {"items": []}

        app.register_blueprint(inbox)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(await check_unique_routes(app))
        detail = checks.RESULTS[-1]["detail"]
        self.assertIn("GET /api/notifications", detail)
        self.assertIn("inbox.own_notifications", detail)

    async def test_without_stk_notification_the_app_owns_the_path(self):
        app = Stk(__name__, config=TestingConfig)
        rules = {r.rule for r in app.url_map.iter_rules()}
        self.assertNotIn("/api/notifications", rules)
        self.assertNotIn("stk_notifications", app.jinja_env.globals)
