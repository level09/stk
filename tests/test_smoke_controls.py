"""Smoke must fail each broken page and pass the healthy one, in a real browser.

The other smoke tests hand build_smoke_report findings directly; these prove the
browser measurements that produce those findings actually fire.
"""

import tempfile
import threading
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from stk.cli.smoke import _visit_smoke_page, build_smoke_report

PAGES = {
    "healthy": "<div id='app'><h1>Invoices</h1><button class='v-btn'"
    " style='color:#111;background:#fff'>Add</button></div>",
    "cloaked": "<style>[v-cloak]{display:none}</style>"
    "<div id='app' v-cloak><h1>Invoices</h1></div>",
    "blank": "<div id='app'></div>",
    "invisible": "<div id='app'><h1>Invoices</h1><button class='v-btn'"
    " style='color:#fff;background:#fff'>Add</button></div>",
    "broken-asset": "<div id='app'><h1>Invoices</h1>"
    "<script src='/missing.js'></script></div>",
    "script-error": "<div id='app'><h1>Invoices</h1>"
    "<script>undefinedFunction()</script></div>",
}


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


class SmokeControlsTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        try:
            from playwright.async_api import async_playwright

            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch()
        except Exception as exc:  # no Playwright or no browser installed
            self.skipTest(f"chromium unavailable: {exc}")
        self.folder = tempfile.TemporaryDirectory()
        for name, body in PAGES.items():
            Path(self.folder.name, f"{name}.html").write_text(
                f"<!doctype html><html><body>{body}</body></html>"
            )
        handler = partial(_Quiet, directory=self.folder.name)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base_url = f"http://127.0.0.1:{self.server.server_address[1]}"

    async def asyncTearDown(self):
        await self.browser.close()
        await self.playwright.stop()
        self.server.shutdown()
        self.folder.cleanup()

    async def test_every_broken_page_fails_and_the_healthy_one_passes(self):
        context = await self.browser.new_context()
        with tempfile.TemporaryDirectory() as shots, _chdir(shots):
            visits = [
                await _visit_smoke_page(context, self.base_url, name, f"/{name}.html")
                for name in PAGES
            ]
        await context.close()
        report = build_smoke_report(visits, "dashboard.png")
        problems = {
            page["name"]: " | ".join(page["problems"]) for page in report["pages"]
        }

        self.assertEqual(problems.pop("healthy"), "")
        expected = {
            "cloaked": "Vue did not mount",
            "blank": "page is blank",
            "invisible": 'invisible text: "Add"',
            "broken-asset": "404",
            "script-error": "undefinedFunction",
        }
        for name, reason in expected.items():
            self.assertIn(reason, problems[name], name)


class _chdir:
    """Screenshots land in .stk/smoke under the working directory."""

    def __init__(self, path):
        self.path = path

    def __enter__(self):
        import os

        self.old = os.getcwd()
        os.chdir(self.path)
        Path(".stk/smoke").mkdir(parents=True)

    def __exit__(self, *exc):
        import os

        os.chdir(self.old)
