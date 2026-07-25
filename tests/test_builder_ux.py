"""Watch loop, doctor report, and remedies: the parts that must not lie."""

import tempfile
import unittest
from pathlib import Path

from stk.cli import watch
from stk.cli.doctor import build_doctor_report
from stk.cli.reports import (
    REMEDIES,
    VERIFY_COMMANDS,
    WATCHED_SUFFIXES,
    build_verify_report,
)


class WatchScanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, relative, content="x = 1\n"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_scan_only_collects_source_files(self):
        kept = self.write("stk/views.py")
        self.write("stk/static/app.css", "body{}")
        self.write("notes.md", "hello")
        self.write("__pycache__/views.cpython-312.pyc", "junk")
        self.write("instance/stk.db", "junk")

        found = set(watch.scan(self.root))

        self.assertIn(kept, found)
        self.assertIn(self.root / "stk/static/app.css", found)
        self.assertNotIn(self.root / "notes.md", found)
        self.assertFalse([p for p in found if "__pycache__" in p.parts])
        self.assertFalse([p for p in found if "instance" in p.parts])

    def test_changed_reports_edits_additions_and_deletions(self):
        first = self.write("stk/a.py")
        before = watch.scan(self.root)

        first.write_text("x = 2\n")
        import os

        os.utime(first, (0, 0))  # deterministic mtime change
        added = self.write("stk/b.py")
        after = watch.scan(self.root)

        self.assertEqual(watch.changed(before, after), sorted([first, added]))
        # A file that disappears counts as a change too.
        added.unlink()
        self.assertEqual(watch.changed(after, watch.scan(self.root)), [added])

    def test_checks_are_selected_by_file_kind(self):
        py = self.root / "stk/models.py"
        css = self.root / "stk/static/app.css"

        self.assertIn("migration-drift", watch.checks_for([py], WATCHED_SUFFIXES))
        self.assertNotIn("migration-drift", watch.checks_for([css], WATCHED_SUFFIXES))
        self.assertEqual(watch.checks_for([], WATCHED_SUFFIXES), [])


class RemedyTest(unittest.TestCase):
    def test_every_verify_check_names_its_remedy(self):
        for name, _command in VERIFY_COMMANDS:
            self.assertIn(name, REMEDIES, f"{name} has no remedy")

    def test_report_carries_the_remedy(self):
        report = build_verify_report(
            [("ruff", ["ruff", "check", "."])],
            runner=lambda command: (1, "boom", ""),
        )

        check = report["checks"][0]
        self.assertEqual(check["status"], "failed")
        self.assertEqual(check["remedy"], REMEDIES["ruff"])


class DoctorTest(unittest.TestCase):
    def test_report_covers_every_area_and_grades_itself(self):
        report = build_doctor_report()

        names = {finding["name"] for finding in report["findings"]}
        self.assertLessEqual(
            {
                "env file",
                "secrets",
                "database",
                "migrations",
                "admin user",
                "assets",
                "agent login",
            },
            names,
        )
        self.assertIn(report["status"], {"ok", "warn", "fail"})
        for finding in report["findings"]:
            if finding["status"] != "ok":
                self.assertTrue(finding["remedy"], f"{finding['name']} has no remedy")


if __name__ == "__main__":
    unittest.main()
