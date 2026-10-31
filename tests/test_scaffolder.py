"""Unit tests for the stk scaffolders: `stk init` and `stk new`.

Rendering is tested as pure functions. The integration tests run the real
commands in subprocesses against a fresh app in a temp directory, because each
step must see the app as a new process would.
"""

import ast
import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

from alembic.script import ScriptDirectory

import stk
from stk.migrations import build_alembic_config
from stk.scaffold.generator import RESERVED, _add_extension, validate_name
from stk.scaffold.templates import (
    plural,
    render_init,
    render_models,
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
        src = render_init("widget", "acme")
        ast.parse(src)

    def test_is_non_empty(self):
        self.assertTrue(render_init("widget", "acme").strip())


class RenderInitContentTests(unittest.TestCase):
    def test_registers_blueprint_and_sidebar_entry(self):
        src = render_init("blog_post", "acme")
        self.assertIn("from acme.blog_post.views import bp_blog_post", src)
        self.assertIn("app.register_blueprint(bp_blog_post)", src)
        self.assertIn('"to": "/blog_posts/"', src)
        self.assertIn('"title": "Blog Posts"', src)


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
        self.src = render_views("demo_item", "acme")

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


class PluralTests(unittest.TestCase):
    def test_pages_use_the_english_plural(self):
        cases = {
            "invoice_line": "invoice_lines",
            "status": "statuses",
            "box": "boxes",
            "batch": "batches",
            "category": "categories",
            "day": "days",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(plural(name), expected)


class LocalSourceTests(unittest.TestCase):
    def test_source_installs_stkit_from_a_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            checkout = Path(stk.__file__).parent.parent
            result = _stk("init", "acme", "--source", str(checkout), cwd=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            sources = tomllib.loads((Path(tmp) / "acme/pyproject.toml").read_text())[
                "tool"
            ]["uv"]["sources"]
            self.assertTrue(sources["stkit"]["editable"])
            self.assertTrue(
                (Path(tmp) / "acme" / sources["stkit"]["path"]).samefile(checkout)
            )


class AddExtensionTests(unittest.TestCase):
    APP = (
        "from stk import Stk\n\n"
        "from acme.settings import Config\n\n"
        "extensions = []\n\n"
        "app = Stk(__name__, config=Config, extensions=extensions)\n"
    )

    def test_first_extension_adds_import_and_entry(self):
        source = _add_extension(self.APP, "acme", "widget")
        self.assertIn(
            "from acme import widget\nfrom acme.settings import Config", source
        )
        self.assertIn("extensions = [widget]", source)

    def test_later_extensions_keep_order_and_one_import_line(self):
        source = _add_extension(self.APP, "acme", "widget")
        source = _add_extension(source, "acme", "gadget")
        self.assertIn("from acme import gadget, widget\n", source)
        self.assertIn("extensions = [widget, gadget]", source)

    def test_missing_list_says_what_to_do(self):
        with self.assertRaises(RuntimeError):
            _add_extension("app = Stk(__name__)\n", "acme", "widget")


def _stk(*args, cwd):
    return subprocess.run(
        [sys.executable, "-m", "stk", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def _package_digest():
    package = Path(stk.__file__).parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            digest.update(str(path).encode() + path.read_bytes())
    return digest.hexdigest()


class InitAndNewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="stk-scaffold-test-")
        cls.before = _package_digest()
        cls.init = _stk("init", "acme", cwd=cls.tmp.name)
        cls.app = Path(cls.tmp.name) / "acme"
        cls.new = _stk("new", "widget", cwd=cls.app)
        cls.second = _stk("new", "gadget", "--no-migrate", cwd=cls.app)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_init_writes_a_thin_app_package(self):
        self.assertEqual(self.init.returncode, 0, self.init.stderr)
        pyproject = (self.app / "pyproject.toml").read_text()
        self.assertIn('app = "acme.app:app"', pyproject)
        self.assertIn(f'"stkit>={stk.__version__},<', pyproject)
        self.assertNotIn("[tool.uv.sources]", pyproject)
        for name in (
            ".gitignore",
            ".env-sample",
            "acme/settings.py",
            "Dockerfile",
            ".github/workflows/checks.yml",
        ):
            self.assertTrue((self.app / name).is_file(), name)
        env = (self.app / ".env").read_text()
        self.assertNotIn("\nSECRET_KEY=\n", env)
        self.assertNotIn("__app__", (self.app / "Dockerfile").read_text())
        # Agents working on the app get stk's rules and skills.
        self.assertIn(
            "## Rules that fail silently", (self.app / "CLAUDE.md").read_text()
        )
        self.assertTrue((self.app / "AGENTS.md").samefile(self.app / "CLAUDE.md"))
        self.assertTrue((self.app / ".agents/skills/stk-blueprint/SKILL.md").is_file())

    def test_init_refuses_an_existing_directory(self):
        result = _stk("init", "acme", cwd=self.tmp.name)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already exists", result.stderr)

    def test_new_writes_the_extension_and_lists_it(self):
        self.assertEqual(self.new.returncode, 0, self.new.stderr)
        self.assertEqual(self.second.returncode, 0, self.second.stderr)
        for name in (
            "__init__.py",
            "models.py",
            "views.py",
            "templates/widget/index.html",
        ):
            self.assertTrue((self.app / "acme" / "widget" / name).is_file(), name)
        for name in ("__init__.py", "models.py", "views.py"):
            ast.parse((self.app / "acme" / "widget" / name).read_text())
        app_module = (self.app / "acme" / "app.py").read_text()
        self.assertIn("from acme import gadget, widget", app_module)
        self.assertIn("extensions = [widget, gadget]", app_module)

    def test_new_starts_the_app_lineage_after_stk(self):
        (revision,) = (self.app / "acme" / "migrations").glob("*.py")
        assigned = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in ast.parse(revision.read_text()).body
            if isinstance(node, ast.Assign)
        }
        self.assertEqual(assigned["branch_labels"], ("acme",))
        core = ScriptDirectory.from_config(build_alembic_config(url="sqlite://"))
        self.assertEqual(assigned["depends_on"], core.get_revision("stk@head").revision)
        # Formatted by the app's ruff config.
        self.assertIn('op.create_table(\n        "widget",', revision.read_text())

    def test_both_lineages_match_the_models(self):
        # gadget was scaffolded without a migration, so it is the only drift.
        result = _stk("db", "check", cwd=self.app)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("add_table: gadget", result.stdout)
        self.assertNotIn("widget", result.stdout)

    def test_extensions_serve_their_pages(self):
        result = _stk("inspect", "routes", "--json", cwd=self.app)
        self.assertEqual(result.returncode, 0, result.stderr)
        rules = {route["rule"] for route in json.loads(result.stdout)}
        self.assertLessEqual({"/widgets/", "/api/widgets", "/gadgets/"}, rules)

    def test_new_never_touches_stk(self):
        self.assertEqual(_package_digest(), self.before)

    def test_new_refuses_duplicates_and_reserved_names(self):
        for name in ("widget", "user"):
            with self.subTest(name=name):
                result = _stk("new", name, "--no-migrate", cwd=self.app)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
