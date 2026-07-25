"""The `stk` command must expose the whole framework without QUART_APP set."""

import unittest

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
        """create_app is baked in, so subcommands need no --app or QUART_APP."""
        result = self.runner.invoke(main, ["shell", "--help"])

        self.assertEqual(result.exit_code, 0)
        self.assertIn("--command", result.output)


if __name__ == "__main__":
    unittest.main()
