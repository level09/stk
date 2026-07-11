import unittest
from datetime import datetime
from unittest.mock import patch

from quart_security import hash_password

import stk.extensions as ext
from stk.agent_login import create_agent_login_token, read_agent_login_token
from stk.app import create_app
from stk.commands import (
    _command_runner,
    build_context_report,
    build_project_report_html,
    build_routes_report,
    build_smoke_report,
    build_verify_report,
    smoke_exit_code,
)
from stk.user.models import Role, User


class AgentOperabilityTests(unittest.TestCase):
    def test_routes_report_exposes_registered_routes(self):
        app = create_app()

        routes = build_routes_report(app)
        by_rule = {route["rule"]: route for route in routes}

        self.assertEqual(by_rule["/"]["blueprint"], "public")
        self.assertIn("GET", by_rule["/"]["methods"])
        self.assertEqual(by_rule["/dashboard/"]["blueprint"], "portal")
        self.assertIn("auth", by_rule["/dashboard/"])
        self.assertIn("source", by_rule["/dashboard/"])
        self.assertTrue(by_rule["/users/"]["auth"]["required"])
        self.assertEqual(by_rule["/users/"]["auth"]["source"], "blueprint")

    def test_context_report_exposes_routes_and_models(self):
        report = build_context_report(create_app())

        self.assertEqual(set(report), {"routes", "models"})
        self.assertIn("user", report["models"])
        user_columns = {c["name"]: c for c in report["models"]["user"]["columns"]}
        self.assertTrue(user_columns["id"]["primary_key"])
        self.assertIn("email", user_columns)

    def test_verify_report_records_command_results(self):
        calls = []

        def runner(command):
            calls.append(command)
            return 0, "ok", ""

        report = build_verify_report([("sample", ["sample", "check"])], runner=runner)

        self.assertEqual(calls, [["sample", "check"]])
        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["checks"][0]["name"], "sample")
        self.assertEqual(report["checks"][0]["returncode"], 0)

    def test_verify_report_allows_skipped_optional_checks(self):
        report = build_verify_report(
            [("ruff", ["ruff", "check", "."])],
            runner=lambda command: (None, "", "ruff not installed"),
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["checks"][0]["status"], "skipped")

    def test_command_runner_reports_missing_ruff_as_skipped(self):
        with patch("stk.commands.subprocess.run") as run:
            run.side_effect = FileNotFoundError

            returncode, stdout, stderr = _command_runner(["ruff", "check", "."])

        self.assertIsNone(returncode)
        self.assertEqual(stdout, "")
        self.assertEqual(stderr, "ruff not installed")

    def test_project_report_html_includes_routes_and_verification_status(self):
        app = create_app()
        routes = build_routes_report(app)
        verify_report = {"status": "passed", "checks": []}

        html = build_project_report_html(routes, verify_report)

        self.assertIn("STK Project Report", html)
        self.assertIn("/login", html)
        self.assertIn("/dashboard/", html)
        self.assertIn("passed", html)

    def test_agent_operability_commands_are_registered(self):
        app = create_app()

        self.assertIn("inspect", app.cli.commands)
        self.assertIn("verify", app.cli.commands)
        self.assertIn("smoke", app.cli.commands)
        self.assertIn("report", app.cli.commands)
        self.assertNotIn("explain", app.cli.commands)

    def test_smoke_report_marks_only_behavioral_failures_as_failed(self):
        report = build_smoke_report(
            [
                {
                    "name": "login",
                    "path": "/login",
                    "status": 200,
                    "console": [{"type": "warning", "text": "slow asset"}],
                    "failed_requests": [],
                },
                {
                    "name": "dashboard",
                    "path": "/dashboard/",
                    "status": 500,
                    "console": [{"type": "error", "text": "ReferenceError"}],
                    "failed_requests": [
                        {"url": "http://127.0.0.1/static/missing.js", "failure": "404"}
                    ],
                },
            ],
            dashboard_screenshot=".stk/smoke/dashboard.png",
        )

        self.assertEqual(report["status"], "failed")
        self.assertEqual(smoke_exit_code(report), 1)
        self.assertEqual(report["pages"][0]["status"], "passed")
        self.assertEqual(report["pages"][1]["status"], "failed")
        self.assertIn("HTTP 500", report["pages"][1]["problems"])
        self.assertIn("console error: ReferenceError", report["pages"][1]["problems"])
        self.assertIn(
            "request failed: http://127.0.0.1/static/missing.js 404",
            report["pages"][1]["problems"],
        )


class AgentLoginConfigTests(unittest.TestCase):
    def test_agent_login_is_disabled_by_default(self):
        app = create_app()

        self.assertFalse(app.config["STK_ENABLE_AGENT_LOGIN"])
        self.assertEqual(app.config["STK_ENV"], "production")
        self.assertNotIn("agent_login.agent_login", app.view_functions)


class AgentLoginEnabledConfig:
    SECRET_KEY = "test-secret"
    SECURITY_PASSWORD_SALT = "test-salt"
    SQLALCHEMY_DATABASE_URI = "sqlite+aiosqlite:///:memory:"
    SESSION_TYPE = None
    STK_ENV = "development"
    STK_ENABLE_AGENT_LOGIN = True
    STK_AGENT_LOGIN_MAX_TTL_SECONDS = 60


class AgentLoginUnsafeConfig(AgentLoginEnabledConfig):
    STK_ENV = "production"
    TESTING = False


class AgentLoginTestingConfig(AgentLoginEnabledConfig):
    TESTING = True
    STK_ENV = "production"


class AgentLoginBlueprintTests(unittest.TestCase):
    def test_agent_login_registers_in_development_only_when_enabled(self):
        app = create_app(AgentLoginEnabledConfig)

        self.assertIn("agent_login.agent_login", app.view_functions)

    def test_agent_login_registers_when_testing_even_if_env_is_production(self):
        app = create_app(AgentLoginTestingConfig)

        self.assertIn("agent_login.agent_login", app.view_functions)

    def test_agent_login_crashes_when_enabled_in_production(self):
        with self.assertRaisesRegex(RuntimeError, "agent login cannot be enabled"):
            create_app(AgentLoginUnsafeConfig)


class AgentLoginTokenTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_login_token_round_trips_user_and_next_path(self):
        app = create_app(AgentLoginTestingConfig)

        async with app.app_context():
            token = create_agent_login_token("admin@example.com", "/dashboard/")
            payload = read_agent_login_token(token, max_age=60)

        self.assertEqual(payload["email"], "admin@example.com")
        self.assertEqual(payload["next"], "/dashboard/")

    async def test_agent_login_token_rejects_external_redirect(self):
        app = create_app(AgentLoginTestingConfig)

        async with app.app_context():
            with self.assertRaisesRegex(ValueError, "next path must be local"):
                create_agent_login_token("admin@example.com", "https://evil.test")


class AgentLoginRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_agent_login_rejects_missing_token(self):
        app = create_app(AgentLoginTestingConfig)

        async with app.test_client() as client:
            response = await client.get("/_test/login")

        self.assertEqual(response.status_code, 400)

    async def test_agent_login_rejects_non_example_user(self):
        app = create_app(AgentLoginTestingConfig)

        async with app.app_context():
            token = create_agent_login_token("real@company.com", "/dashboard/")

        async with app.test_client() as client:
            response = await client.get(f"/_test/login?token={token}")

        self.assertEqual(response.status_code, 403)


class AgentLoginSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = create_app(AgentLoginTestingConfig)
        async with ext.engine.begin() as conn:
            await conn.run_sync(Role.metadata.create_all)

    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def test_agent_login_creates_authenticated_session(self):
        async with ext.async_session_factory() as session:
            role = Role(name="admin")
            user = User(
                email="admin@example.com",
                name="Admin",
                password=hash_password("TestPassword123!"),
                active=True,
                confirmed_at=datetime.now(),
            )
            user.roles.append(role)
            session.add(user)
            await session.commit()

        async with self.app.app_context():
            token = create_agent_login_token("admin@example.com", "/dashboard/")

        async with self.app.test_client() as client:
            response = await client.get(f"/_test/login?token={token}")
            self.assertEqual(response.status_code, 302)

            dashboard = await client.get("/dashboard/")

        self.assertNotEqual(dashboard.status_code, 401)


class AgentLoginVerificationTests(unittest.TestCase):
    def test_verify_report_marks_agent_login_disabled_as_safe(self):
        app = create_app()
        routes = build_routes_report(app)

        self.assertNotIn("/_test/login", {route["rule"] for route in routes})


if __name__ == "__main__":
    unittest.main()
