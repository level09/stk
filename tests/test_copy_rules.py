import unittest

from stk.cli.copy_rules import (
    broken_value,
    copy_findings,
    hex_id,
    one_plural,
    raw_score,
    repeated_rows,
    snake_case,
    uuid,
)
from stk.cli.smoke import build_smoke_report, smoke_exit_code


class CopyRuleTests(unittest.TestCase):
    def assertRule(self, rule, flagged, clean):
        for text in flagged:
            self.assertTrue(rule(text), f"{rule.__name__} missed: {text!r}")
        for text in clean:
            self.assertEqual(rule(text), [], f"{rule.__name__} flagged: {text!r}")

    def test_uuid(self):
        self.assertRule(
            uuid,
            ["Owner 3f2b8c1e-9a4d-4e2f-8b1c-0d9e7f6a5b4c"],
            ["Owner Jane Doe", "Call 555-1234-5678"],
        )

    def test_hex_id(self):
        self.assertRule(
            hex_id,
            ["Request 1fbaac41 failed", "texteb148f8f"],
            [
                "SHA-256: 9f86d081884c7d65",
                "Total 1234567",
                "Accepted",
                "Owner 3f2b8c1e-9a4d-4e2f-8b1c-0d9e7f6a5b4c",
            ],
        )

    def test_snake_case(self):
        self.assertRule(
            snake_case,
            ["Status: pending_review", "Sorted by created_at"],
            ["jane_doe@example.com", "/static/app_icon.png", "STK_ENV", "Pending"],
        )

    def test_raw_score(self):
        self.assertRule(
            raw_score,
            ["Match score 0.8731", "confidence: .92", "Similarity=0.5"],
            ["Score: high", "Version 3.5", "Confidence: strong"],
        )

    def test_one_plural(self):
        self.assertRule(
            one_plural,
            ["1 items", "Showing 1 results", "Due in 1 days"],
            ["1 item", "2 items", "1 status", "1 is open", "1-1 of 1", "v1 docs"],
        )

    def test_one_plural_skips_a_number_and_label_on_separate_lines(self):
        self.assertEqual(one_plural("1\nUsers"), [])

    def test_broken_value(self):
        self.assertRule(
            broken_value,
            ["Name: undefined", "Due null", "Total NaN", "Owner [object Object]"],
            ["Nullable fields", "Undefined behaviour is documented", "Banana"],
        )

    def test_repeated_rows(self):
        self.assertEqual(
            repeated_rows([["Jane Doe", "Jane Doe", "Jane Doe", "Sam Roe"]]),
            ["Jane Doe (x3)"],
        )
        self.assertEqual(repeated_rows([["Jane Doe", "Jane Doe", "Sam Roe"]]), [])
        self.assertEqual(repeated_rows([["", "", ""], ["12", "12", "12"]]), [])

    def test_allow_list_drops_matching_snippets(self):
        text = "Signed with Ed25519 key 4a5b6c7d8e"
        self.assertEqual(copy_findings(text)[0]["rule"], "hex-id")
        self.assertEqual(copy_findings(text, allow=[r"Ed25519 key"]), [])


class SmokeCopyReportTests(unittest.TestCase):
    def test_copy_finding_fails_smoke_with_rule_and_text(self):
        page = {
            "name": "/invoices/",
            "path": "/invoices/",
            "status": 200,
            "text": "Showing 1 items",
            "rows": [],
        }
        report = build_smoke_report([page], ".stk/smoke/dashboard.png")
        self.assertEqual(smoke_exit_code(report), 1)
        self.assertEqual(
            report["pages"][0]["copy"],
            [{"rule": "one-plural", "text": "Showing 1 items"}],
        )
        self.assertIn(
            'reads badly (one-plural): "Showing 1 items"',
            report["pages"][0]["problems"],
        )

        allowed = build_smoke_report([page], ".stk/smoke/dashboard.png", ["1 items"])
        self.assertEqual(smoke_exit_code(allowed), 0)


if __name__ == "__main__":
    unittest.main()
