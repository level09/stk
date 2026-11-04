"""An app composes stk: its files win over its extensions', which win over stk's."""

import hashlib
import importlib
import json
import re
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from stk.app import Stk
from stk.settings import TestingConfig

FILES = {
    "tapp/__init__.py": "",
    # The app overrides stk's index page and extends stk's original layout.
    "tapp/templates/index.html": textwrap.dedent(
        """\
        {% extends "stk/layout.html" %}
        {% block title %}App title{% endblock %}
        {% block content %}APP INDEX {% include "ext_only.html" %}{% endblock %}
        """
    ),
    "tapp/templates/_head.html": '<meta name="tapp-head">',
    # A top-bar-only shell: no drawer, the app's links in the user menu.
    "tapp/templates/topbar.html": textwrap.dedent(
        """\
        {% extends "stk/layout.html" %}
        {% block sidebar %}{% endblock %}
        {% block user_menu %}<v-list-item href="/kyc/">KYC</v-list-item>{{ super() }}{% endblock %}
        """
    ),
    "tapp/static/css/app.css": "/* the app's */",
    "tapp/static/js/page.js": 'import "./shared.js";',
    "tapp/static/js/shared.js": "// the app's, shadowing the extension's",
    "tapp/first/__init__.py": textwrap.dedent(
        """\
        from tapp.first import models


        def init_app(app):
            app.config["SEEN_MODELS_FIRST"] = models.LOADED
            app.navigation.append({"title": "First", "to": "/first/"})
        """
    ),
    "tapp/first/models.py": "LOADED = True\n",
    "tapp/first/templates/ext_only.html": "FIRST",
    "tapp/first/templates/index.html": "the extension's, shadowed by the app's",
    "tapp/first/static/css/app.css": "/* the first extension's */",
    "tapp/first/static/css/ext.css": "/* first */",
    "tapp/first/static/js/shared.js": "// the first extension's",
    "tapp/first/static/js/lib/util.mjs": "export const x = 1;",
    "tapp/second/__init__.py": textwrap.dedent(
        """\
        def init_app(app):
            app.navigation.append({"title": "Second", "to": "/second/"})
        """
    ),
    "tapp/second/static/css/ext.css": "/* second */",
}


class CompositionTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="stk-compose-")
        for name, text in FILES.items():
            path = Path(cls.tmp.name) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        sys.path.insert(0, cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        sys.path.remove(cls.tmp.name)
        for name in [m for m in sys.modules if m == "tapp" or m.startswith("tapp.")]:
            del sys.modules[name]
        cls.tmp.cleanup()

    def setUp(self):
        extensions = [
            importlib.import_module("tapp.first"),
            importlib.import_module("tapp.second"),
        ]
        self.app = Stk("tapp", config=TestingConfig, extensions=extensions)

    async def test_app_template_wins_and_can_extend_the_core_one(self):
        response = await self.app.test_client().get("/")
        page = await response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("APP INDEX FIRST", page)
        self.assertIn("<title>App title</title>", page)
        self.assertIn("stkNavigation", page)  # rendered by stk's layout

    async def test_app_head_reaches_every_layout(self):
        """Pages empty or replace the css block; the head partial sits outside it."""
        from quart import render_template

        self.assertIn(
            'name="tapp-head"',
            await (await self.app.test_client().get("/login")).get_data(True),
        )
        async with self.app.test_request_context("/"):
            for layout in ("layout.html", "auth_layout.html", "login-layout.html"):
                page = await render_template(layout)
                self.assertIn('name="tapp-head"', page, layout)

    async def test_layout_without_the_sidebar_keeps_the_app_bar(self):
        from types import SimpleNamespace

        from quart import render_template

        user = SimpleNamespace(is_authenticated=True, name="Ann", email="a@example.com")
        async with self.app.test_request_context("/"):
            full = await render_template("layout.html", current_user=user)
            bar = await render_template("topbar.html", current_user=user)
        self.assertIn("<v-navigation-drawer", full)
        self.assertIn("ti-menu-2", full)
        self.assertNotIn("<v-navigation-drawer", bar)
        self.assertNotIn("ti-menu-2", bar)  # no drawer to open
        self.assertLess(bar.index('href="/kyc/"'), bar.index("Change Password"))
        self.assertIn("<theme-switcher>", bar)

    def test_doctor_names_copies_of_stk_files_but_not_slots(self):
        from stk.cli.doctor import _check_overrides

        finding = _check_overrides(self.app)
        self.assertEqual(finding["status"], "warn")
        # index.html and _head.html are slots, topbar.html extends stk's layout.
        self.assertIn(
            "copies of stk files miss its fixes: static/css/app.css", finding["detail"]
        )
        self.assertNotIn("html", finding["detail"])

    async def test_static_files_resolve_app_then_extensions_in_order(self):
        client = self.app.test_client()
        app_css = await (await client.get("/static/css/app.css")).get_data(True)
        ext_css = await (await client.get("/static/css/ext.css")).get_data(True)
        core = await client.get("/static/js/config.js")
        self.assertEqual(app_css, "/* the app's */")
        self.assertEqual(ext_css, "/* first */")
        self.assertEqual(core.status_code, 200)
        missing = await client.get("/static/../settings.py")
        self.assertEqual(missing.status_code, 404)

    async def test_versioned_urls_hash_the_file_that_will_be_served(self):
        async with self.app.test_request_context("/"):
            from quart import url_for

            app_url = url_for("static", filename="css/app.css")
            core_url = url_for("static", filename="css/layout.css")
        self.assertRegex(app_url, r"\?v=[0-9a-f]{12}$")
        self.assertRegex(core_url, r"\?v=[0-9a-f]{12}$")

    def test_navigation_lists_extension_pages_under_dashboard_in_order(self):
        titles = [
            item.get("title") or item.get("heading")
            for item in self.app.jinja_env.globals["stk_navigation"]()
        ]
        self.assertEqual(
            titles[:5], ["Main", "Dashboard", "First", "Second", "Account"]
        )

    def test_app_navigation_is_the_apps_entries_alone(self):
        titles = [i["title"] for i in self.app.jinja_env.globals["app_navigation"]()]
        self.assertEqual(titles, ["First", "Second"])

    async def test_import_map_versions_every_module_as_it_will_be_served(self):
        page = await (await self.app.test_client().get("/")).get_data(as_text=True)
        tag = re.search(r'<script type="importmap">(.*?)</script>', page)
        imports = json.loads(tag.group(1))["imports"]
        for name in ("js/page.js", "js/shared.js", "js/lib/util.mjs", "js/config.js"):
            self.assertRegex(imports[f"/static/{name}"], r"\?v=[0-9a-f]{12}$")
        async with self.app.test_request_context("/"):
            from quart import url_for

            shared = url_for("static", filename="js/shared.js")
        self.assertEqual(imports["/static/js/shared.js"], shared)
        app_digest = hashlib.sha256(b"// the app's, shadowing the extension's")
        self.assertTrue(shared.endswith(app_digest.hexdigest()[:12]))
        self.assertNotIn("/static/css/app.css", imports)

    def test_extension_models_load_before_init_app(self):
        self.assertTrue(self.app.config["SEEN_MODELS_FIRST"])

    def test_missing_secrets_fail_when_the_app_is_built(self):
        class NoSecret(TestingConfig):
            SECRET_KEY = None

        with self.assertRaisesRegex(ValueError, "SECRET_KEY"):
            Stk("tapp", config=NoSecret)


if __name__ == "__main__":
    unittest.main()
