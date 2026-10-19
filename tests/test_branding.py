import pathlib
import unittest

from stk.app import create_app
from stk.settings import Config


class AcmeConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///:memory:"
    SESSION_TYPE = None
    QUART_RATE_LIMITER_ENABLED = False
    APP_NAME = "Acme"


class BrandingTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_uses_app_name(self):
        app = create_app(AcmeConfig)
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
