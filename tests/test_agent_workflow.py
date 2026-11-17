"""The repair agent must never be able to change what grades it."""

import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).parent.parent / ".github" / "workflows" / "agent.yml"


def protected():
    match = re.search(r"PROTECTED: '([^']+)'", WORKFLOW.read_text())
    return re.compile(match.group(1))


class AgentWorkflowTest(unittest.TestCase):
    def test_every_grader_file_is_protected(self):
        pattern = protected()
        for path in (
            "stk/checks.py",
            "stk/cli/smoke.py",
            "stk/cli/reports.py",
            "stk/cli/copy_rules.py",
            "stk/cli/watch.py",
            "stk/cli/database.py",
            "stk/migrations/__init__.py",
            "stk/migrations/env.py",
            "tests/test_cli.py",
            ".github/workflows/agent.yml",
        ):
            self.assertTrue(pattern.search(path), path)

    def test_the_fixes_it_is_asked_for_stay_open(self):
        pattern = protected()
        for path in (
            "pyproject.toml",
            "uv.lock",
            "stk/migrations/versions/stk_0009_example.py",
            "stk/tasks/__init__.py",
        ):
            self.assertFalse(pattern.search(path), path)
