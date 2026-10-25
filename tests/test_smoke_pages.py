import unittest

from quart import Blueprint

from stk.app import Stk
from stk.cli.reports import build_routes_report
from stk.cli.smoke import (
    build_smoke_report,
    discover_smoke_paths,
    machine_paths,
    smoke_exit_code,
)
from stk.security import csrf_exempt
from stk.settings import TestingConfig


class SmokePageDiscoveryTests(unittest.TestCase):
    def test_discovers_parameterless_admin_pages_only(self):
        app = Stk(__name__, config=TestingConfig)
        crm = Blueprint("smoke_demo", __name__)

        @crm.get("/smoke-demo/staff")
        async def staff():
            return ""

        @crm.get("/smoke-demo/staff/<int:id>")
        async def staff_member(id):
            return ""

        @crm.get("/api/smoke-demo/staff")
        async def api_staff():
            return ""

        @crm.get("/smoke-demo/webhook")
        async def webhook_verify():
            return ""

        @crm.post("/smoke-demo/webhook")
        @csrf_exempt
        async def webhook():
            return ""

        @crm.websocket("/smoke-demo/live")
        async def live():
            return None

        app.register_blueprint(crm)
        paths = discover_smoke_paths(build_routes_report(app), machine_paths(app))

        self.assertIn("/smoke-demo/staff", paths)
        self.assertIn("/roles/", paths)
        self.assertEqual(paths, sorted(paths))
        for skipped in (
            "/smoke-demo/staff/<int:id>",
            "/smoke-demo/webhook",
            "/smoke-demo/live",
            "/api/smoke-demo/staff",
            "/login",
            "/login/github",
            "/register",
            "/tf-setup",
            "/wan-signin",
            "/mf-recovery",
            "/ws",
            "/users/",
            "/",
        ):
            self.assertNotIn(skipped, paths)


class SmokePageErrorTests(unittest.TestCase):
    def test_uncaught_page_error_fails_smoke(self):
        report = build_smoke_report(
            [
                {
                    "name": "/smoke-demo/staff",
                    "path": "/smoke-demo/staff",
                    "status": 200,
                    "console": [{"type": "pageerror", "text": "TypeError: x is null"}],
                    "failed_requests": [],
                }
            ],
            dashboard_screenshot=".stk/smoke/dashboard.png",
        )
        self.assertEqual(smoke_exit_code(report), 1)
        self.assertIn(
            "uncaught error: TypeError: x is null", report["pages"][0]["problems"]
        )


if __name__ == "__main__":
    unittest.main()
