import re
import unittest
from pathlib import Path

from stk.app import create_app
from stk.qarina.costs import CostLedger
from stk.qarina.knowledge import _namespace_key
from stk.qarina.language import output_language_instruction, resolve_output_language


class QarinaTestConfig:
    SECRET_KEY = "test-secret"
    SECURITY_PASSWORD_SALT = "test-salt"
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///:memory:"
    SESSION_TYPE = None
    TESTING = True


class QarinaIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def test_output_language_auto_detects_arabic_queries(self):
        self.assertEqual(
            resolve_output_language("ما هي آخر التطورات؟", "auto"), "arabic"
        )
        self.assertEqual(resolve_output_language("What happened?", "auto"), "english")

    def test_output_language_override_wins_over_auto_detection(self):
        self.assertEqual(
            resolve_output_language("ما هي آخر التطورات؟", "english"), "english"
        )
        self.assertEqual(resolve_output_language("What happened?", "arabic"), "arabic")

    def test_output_language_instruction_requires_the_selected_language(self):
        self.assertIn("Arabic", output_language_instruction("arabic"))
        self.assertIn("English", output_language_instruction("english"))

    def test_cost_ledger_estimates_openrouter_and_serper_usage(self):
        class Usage:
            prompt_tokens = 1000
            completion_tokens = 500
            total_tokens = 1500

        class Response:
            model = "test-model"
            usage = Usage()

        ledger = CostLedger(
            model_pricing={
                "test-model": {"prompt": 1.0, "completion": 2.0},
            },
            serper_cost_per_query=0.01,
        )
        ledger.record_openrouter(Response(), purpose="research")
        ledger.record_serper("news")

        summary = ledger.summary()

        self.assertEqual(summary["openrouter"]["total_tokens"], 1500)
        self.assertEqual(summary["serper"]["queries"], 1)
        self.assertEqual(summary["estimated_usd"], 0.012)

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

    def test_research_home_keeps_canonical_url_on_show_home(self):
        template = Path("stk/templates/qarina/index.html").read_text()
        match = re.search(
            r"function showHome\(\{ push = false \} = \{\}\) \{.*?\n\}",
            template,
            re.DOTALL,
        )

        self.assertIsNotNone(match)
        home_script = match.group()
        self.assertIn("history.pushState(null, '', '/research/')", home_script)
        self.assertIn("history.replaceState(null, '', '/research/')", home_script)

    def test_research_home_sends_the_selected_output_language(self):
        template = Path("stk/templates/qarina/index.html").read_text()
        agent = Path("stk/qarina/agent.py").read_text()

        self.assertIn('id="output-language"', template)
        self.assertIn('value="auto"', template)
        self.assertIn('value="english"', template)
        self.assertIn('value="arabic"', template)
        self.assertIn("output_language: outputLanguageEl.value", template)
        self.assertIn(
            'resolve_output_language(query, config.get("output_language"))', agent
        )
