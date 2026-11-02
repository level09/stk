"""The `stk` command must expose the whole framework without QUART_APP set."""

import unittest
from unittest.mock import patch

from click.testing import CliRunner

from stk.cli.main import SECTIONS, main


class StkCommandTest(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def test_help_lists_every_command_in_a_section(self):
        result = self.runner.invoke(main, ["--help"])

        self.assertEqual(result.exit_code, 0)
        for title, names in SECTIONS:
            self.assertIn(f"{title}:", result.output)
            for name in names:
                self.assertIn(name, result.output)

    def test_help_has_no_unsectioned_commands(self):
        """Every command belongs to a section, so 'Other' should stay empty."""
        result = self.runner.invoke(main, ["--help"])

        self.assertNotIn("Other:", result.output)

    def test_commands_survive_importing_their_backing_modules(self):
        """A submodule named like its command rebinds the package attribute."""
        from stk.cli.doctor import build_doctor_report  # noqa: F401
        from stk.cli.smoke import build_smoke_report  # noqa: F401

        result = self.runner.invoke(main, ["--help"])

        self.assertIn("doctor", result.output)
        self.assertIn("smoke", result.output)

    def test_version_reports_stk_not_quart(self):
        result = self.runner.invoke(main, ["--version"])

        self.assertEqual(result.exit_code, 0)
        self.assertTrue(result.output.startswith("stk "), result.output)

    def test_app_commands_resolve_without_quart_app_env(self):
        """The app comes from [tool.stk], so subcommands need no --app or QUART_APP."""
        result = self.runner.invoke(main, ["shell", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--command", result.output)


if __name__ == "__main__":
    unittest.main()


class PublicUrlDoctorTest(unittest.TestCase):
    def test_warns_only_outside_development_without_a_public_url(self):
        from stk.cli.doctor import _check_public_url

        self.assertEqual(_check_public_url({})["status"], "warn")
        self.assertEqual(_check_public_url({"STK_ENV": "development"})["status"], "ok")
        set_url = {"STK_PUBLIC_URL": "https://app.example.com"}
        self.assertEqual(_check_public_url(set_url)["status"], "ok")


class DowngradeArgumentTest(unittest.TestCase):
    def test_relative_revision_is_accepted(self):
        with patch("stk.cli.database.run_alembic") as run:
            result = CliRunner().invoke(main, ["db", "downgrade", "-1"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(run.call_args.args[-1], "-1")


class DatabaseCommandTest(unittest.TestCase):
    def test_run_async_builds_the_app_before_touching_the_database(self):
        """`add-role` and `cleanup-sessions` crashed: nothing had built the engine."""
        with (
            patch("stk.cli.base.cli_app") as load,
            patch("stk.tasks.cleanup_expired_sessions") as cleanup,
        ):
            cleanup.side_effect = lambda: _done()
            result = CliRunner().invoke(main, ["cleanup-sessions"])
        self.assertEqual(result.exit_code, 0, result.output)
        load.assert_called()


class RunCommandTest(unittest.TestCase):
    def test_run_on_a_taken_port_names_the_holder(self):
        import os
        import socket

        with socket.socket() as held:
            held.bind(("127.0.0.1", 0))
            held.listen()
            port = held.getsockname()[1]
            result = CliRunner().invoke(main, ["run", "--port", str(port)])

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(f"port {port} is in use", result.output)
        self.assertIn(f"pid {os.getpid()}", result.output)


async def _done():
    return None
