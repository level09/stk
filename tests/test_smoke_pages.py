import subprocess
import sys
import unittest
from unittest.mock import patch

from quart import Blueprint

from stk.app import Stk
from stk.cli.reports import build_routes_report
from stk.cli.smoke import (
    _start_smoke_server,
    _stop_smoke_server,
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


class EventStreamPageTest(unittest.IsolatedAsyncioTestCase):
    """A page that opens an EventSource on load still reaches networkidle."""

    async def test_page_with_open_event_stream_finishes(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        from stk.cli.smoke import _visit_smoke_page

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.send_response(200)
                if self.path == "/events":
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    self.wfile.write(b": open\n\n")
                    self.wfile.flush()
                    threading.Event().wait(30)  # a live stream never ends
                    return
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(
                    b"<p>live</p><script>new EventSource('/events')</script>"
                )

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.shutdown)
        try:
            from playwright.async_api import async_playwright

            playwright = await async_playwright().start()
            browser = await playwright.chromium.launch()
        except Exception as exc:  # no Playwright or no browser installed
            self.skipTest(f"chromium unavailable: {exc}")
        try:
            context = await browser.new_context()
            context.set_default_navigation_timeout(5000)
            base_url = f"http://127.0.0.1:{server.server_port}"
            page = await _visit_smoke_page(context, base_url, "live", "/")
        finally:
            await browser.close()
            await playwright.stop()
        self.assertEqual(page["status"], 200)


class SmokeServerOutputTests(unittest.TestCase):
    def test_server_never_blocks_on_its_own_log(self):
        """An access log past the 64 KB pipe buffer froze the server mid-run."""
        popen = subprocess.Popen
        chatty = [sys.executable, "-c", "print('x' * 200_000)"]
        with patch(
            "stk.cli.smoke.subprocess.Popen", lambda _, **kw: popen(chatty, **kw)
        ):
            server = _start_smoke_server(0, None)
        try:
            self.assertEqual(server.wait(timeout=5), 0)
        finally:
            _stop_smoke_server(server)


class SmokeScreenshotTests(unittest.TestCase):
    def test_each_page_gets_its_own_screenshot_file(self):
        from stk.cli.smoke import screenshot_path

        self.assertEqual(screenshot_path("dashboard").name, "dashboard.png")
        self.assertEqual(screenshot_path("/monitor/runs").name, "monitor-runs.png")
        self.assertEqual(screenshot_path("/").name, "home.png")
