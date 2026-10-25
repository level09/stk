import pathlib
import unittest

from stk.app import Stk
from stk.settings import TestingConfig


class AcmeConfig(TestingConfig):
    APP_NAME = "Acme"


class BrandingTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_uses_app_name(self):
        app = Stk(__name__, config=AcmeConfig)
        response = await app.test_client().get("/login")
        html = await response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Acme", html)
        self.assertNotIn("Project stk", html)
        self.assertNotIn("New to stk", html)

    def test_logo_lives_in_brand_partial(self):
        templates = pathlib.Path(__file__).parent.parent / "stk" / "templates"
        offenders = [
            str(p.relative_to(templates))
            for p in templates.rglob("*.html")
            if p.name != "_brand.html" and "stk.svg" in p.read_text()
        ]
        self.assertEqual(offenders, [])
