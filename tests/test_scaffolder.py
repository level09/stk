"""Unit tests for the stk module scaffolder.

Uses pure-function rendering -- no filesystem I/O except for the integration
test that exercises generate_module() in a temp directory that mirrors the
real tree layout.
"""

import ast
import py_compile
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from stk.scaffold.generator import (
    RESERVED,
    generate_module,
    scaffold_paths,
    validate_name,
)
from stk.scaffold.templates import (
    render_app_import,
    render_app_register,
    render_init,
    render_models,
    render_nav_entry,
    render_template_html,
    render_views,
)


class ValidateNameTests(unittest.TestCase):
    def test_valid_names_pass(self):
        for name in ("blog_post", "invoice", "product2", "order_item"):
            with self.subTest(name=name):
                validate_name(name)  # must not raise

    def test_uppercase_rejected(self):
        with self.assertRaises(ValueError, msg="BlogPost"):
            validate_name("BlogPost")

    def test_leading_digit_rejected(self):
        with self.assertRaises(ValueError):
            validate_name("2things")

    def test_hyphen_rejected(self):
        with self.assertRaises(ValueError):
            validate_name("blog-post")

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            validate_name("")

    def test_reserved_names_rejected(self):
        for name in ("user", "role", "public", "portal", "session", "admin"):
            with self.subTest(name=name):
                with self.assertRaises(ValueError):
                    validate_name(name)

    def test_all_reserved_names_are_lowercase(self):
        for name in RESERVED:
            self.assertEqual(name, name.lower(), f"RESERVED contains uppercase: {name}")


class RenderInitTests(unittest.TestCase):
    def test_is_valid_python(self):
        src = render_init("widget")
        ast.parse(src)

    def test_is_non_empty(self):
        self.assertTrue(render_init("widget").strip())


class RenderModelsTests(unittest.TestCase):
    def setUp(self):
        self.src = render_models("demo_item")

    def test_is_valid_python(self):
        ast.parse(self.src)

    def test_class_name_derived_from_name(self):
        self.assertIn("class DemoItem(Base):", self.src)

    def test_tablename_is_name(self):
        self.assertIn('__tablename__ = "demo_item"', self.src)

    def test_has_created_at(self):
        self.assertIn("created_at", self.src)

    def test_has_to_dict(self):
        self.assertIn("def to_dict(self)", self.src)

    def test_has_from_dict(self):
        self.assertIn("async def from_dict(self, data", self.src)

    def test_imports_base(self):
        self.assertIn("from stk.extensions import Base", self.src)

    def test_no_db_model(self):
        self.assertNotIn("db.Model", self.src)


class RenderViewsTests(unittest.TestCase):
    def setUp(self):
        self.src = render_views("demo_item")

    def test_is_valid_python(self):
        ast.parse(self.src)

    def test_blueprint_name(self):
        self.assertIn('bp_demo_item = Blueprint("demo_item"', self.src)

    def test_list_endpoint(self):
        self.assertIn("/api/demo_items", self.src)

    def test_create_endpoint(self):
        self.assertIn("/api/demo_item/", self.src)

    def test_update_endpoint(self):
        self.assertIn("/api/demo_item/<int:id>", self.src)

    def test_delete_endpoint(self):
        self.assertIn('methods=["DELETE"]', self.src)

    def test_orjson_import(self):
        self.assertIn("import orjson as json", self.src)

    def test_auth_required(self):
        self.assertIn('@auth_required("session")', self.src)

    def test_activity_register(self):
        self.assertIn("Activity.register", self.src)

    def test_no_flask_jsonify(self):
        self.assertNotIn("jsonify", self.src)

    def test_item_wrapper_extraction(self):
        self.assertIn('json_data.get("item", {})', self.src)

    def test_rollback_on_error(self):
        self.assertIn("g.db_session.rollback()", self.src)

    def test_per_page_constant(self):
        self.assertIn("PER_PAGE = 25", self.src)


class RenderTemplateHtmlTests(unittest.TestCase):
    def setUp(self):
        self.src = render_template_html("demo_item")

    def test_extends_layout(self):
        self.assertIn("extends 'layout.html'", self.src)

    def test_delimiters_config(self):
        self.assertIn("delimiters: config.delimiters", self.src)

    def test_layout_mixin(self):
        self.assertIn("mixins: [layoutMixin]", self.src)

    def test_register_stk_components(self):
        self.assertIn("registerStkComponents(app)", self.src)

    def test_vuetify_config(self):
        self.assertIn("config.vuetifyConfig", self.src)

    def test_data_table_server(self):
        self.assertIn("v-data-table-server", self.src)

    def test_tabler_icons(self):
        self.assertIn("ti ti-", self.src)
        self.assertNotIn("mdi-", self.src)

    def test_to_raw_import(self):
        self.assertIn("toRaw", self.src)

    def test_api_url_uses_plural(self):
        self.assertIn("/api/demo_items", self.src)

    def test_no_setup_api(self):
        self.assertNotIn("setup()", self.src)


class RenderNavEntryTests(unittest.TestCase):
    def test_contains_plural_route(self):
        entry = render_nav_entry("widget")
        self.assertIn("'/widgets'", entry)

    def test_role_admin(self):
        entry = render_nav_entry("widget")
        self.assertIn("role: 'admin'", entry)

    def test_title_titlecased(self):
        entry = render_nav_entry("blog_post")
        self.assertIn("'Blog Post'", entry)


class RenderAppHelpersTests(unittest.TestCase):
    def test_import_line(self):
        line = render_app_import("widget")
        self.assertEqual(line, "from stk.widget.views import bp_widget\n")

    def test_register_line(self):
        line = render_app_register("widget")
        self.assertEqual(line, "    app.register_blueprint(bp_widget)\n")


class GenerateModuleIntegrationTests(unittest.TestCase):
    """Exercises generate_module() in a controlled fake tree."""

    # Minimal app.py that contains the anchors generate_module() patches.
    _FAKE_APP_PY = textwrap.dedent(
        """\
        from stk.websocket import ws_bp

        def register_blueprints(app):
            app.register_blueprint(ws_bp)
        """
    )

    # Minimal navigation.js that contains the nav anchor.
    _FAKE_NAV_JS = textwrap.dedent(
        """\
        const stkNavigation = [
          {
            title: 'Activity Logs',
            icon: 'ti ti-history',
            to: '/activities',
            role: 'admin'
          }
        ];
        """
    )

    def _make_fake_root(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="stk-scaffold-test-"))
        (root / "stk").mkdir()
        (root / "stk" / "static" / "js").mkdir(parents=True)
        (root / "stk" / "templates" / "cms").mkdir(parents=True)
        (root / "stk" / "app.py").write_text(self._FAKE_APP_PY)
        (root / "stk" / "static" / "js" / "navigation.js").write_text(self._FAKE_NAV_JS)
        return root

    def setUp(self):
        self.root = self._make_fake_root()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_generates_expected_files(self):
        generate_module("widget", root=self.root)
        paths = scaffold_paths("widget", root=self.root)
        for key, path in paths.items():
            if key in ("app_py", "nav_js"):
                continue
            with self.subTest(key=key):
                self.assertTrue(path.exists(), f"{key} not created at {path}")

    def test_python_files_compile(self):
        generate_module("widget", root=self.root)
        paths = scaffold_paths("widget", root=self.root)
        for key in ("pkg_init", "pkg_models", "pkg_views"):
            with self.subTest(key=key):
                py_compile.compile(str(paths[key]), doraise=True)

    def test_app_py_patched(self):
        generate_module("widget", root=self.root)
        app_text = (self.root / "stk" / "app.py").read_text()
        self.assertIn("from stk.widget.views import bp_widget", app_text)
        self.assertIn("app.register_blueprint(bp_widget)", app_text)

    def test_nav_js_patched(self):
        generate_module("widget", root=self.root)
        nav_text = (self.root / "stk" / "static" / "js" / "navigation.js").read_text()
        self.assertIn("'/widgets'", nav_text)

    def test_idempotent_patch_does_not_duplicate(self):
        generate_module("widget", root=self.root)
        # Simulate re-running (e.g. agent runs new twice)
        generate_module("gadget", root=self.root)
        app_text = (self.root / "stk" / "app.py").read_text()
        self.assertEqual(app_text.count("bp_widget"), 2)  # import + register

    def test_duplicate_name_raises(self):
        generate_module("widget", root=self.root)
        with self.assertRaises(FileExistsError):
            generate_module("widget", root=self.root)

    def test_reserved_name_raises(self):
        with self.assertRaises(ValueError):
            generate_module("user", root=self.root)

    def test_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            generate_module("My-Module", root=self.root)

    def test_template_html_has_correct_api_url(self):
        generate_module("widget", root=self.root)
        tmpl = (self.root / "stk" / "templates" / "cms" / "widget.html").read_text()
        self.assertIn("/api/widgets", tmpl)

    def test_actions_returned(self):
        actions = generate_module("widget", root=self.root)
        self.assertIsInstance(actions, list)
        self.assertTrue(len(actions) >= 4)


if __name__ == "__main__":
    unittest.main()
