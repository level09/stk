import unittest
from unittest.mock import patch

from stk.app import create_app
from stk.commands import (
    _command_runner,
    build_project_report_html,
    build_routes_report,
    build_verify_report,
)


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
        self.assertIn("report", app.cli.commands)
        self.assertNotIn("explain", app.cli.commands)


if __name__ == "__main__":
    unittest.main()
