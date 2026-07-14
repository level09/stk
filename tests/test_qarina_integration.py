import unittest

from stk.app import create_app
from stk.qarina.knowledge import _namespace_key


class QarinaTestConfig:
    SECRET_KEY = "test-secret"
    SECURITY_PASSWORD_SALT = "test-salt"
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///:memory:"
    SESSION_TYPE = None
    TESTING = True


class QarinaIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_knowledge_namespace_is_user_scoped(self):
        self.assertEqual(_namespace_key(7), "user-7")
        self.assertNotEqual(_namespace_key(7), _namespace_key(8))

    def test_knowledge_namespace_rejects_untrusted_path_values(self):
        with self.assertRaises(ValueError):
            _namespace_key("../../shared")

    async def test_research_page_requires_authentication(self):
        app = create_app(QarinaTestConfig)

        async with app.test_client() as client:
            response = await client.get("/research/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["location"])

    def test_research_routes_are_registered(self):
        app = create_app(QarinaTestConfig)
        rules = {rule.rule for rule in app.url_map.iter_rules()}

        self.assertIn("/research/", rules)
        self.assertIn("/research/ws", rules)
        self.assertIn("/research/api/history", rules)
        self.assertIn("/research/api/history/<int:run_id>", rules)
