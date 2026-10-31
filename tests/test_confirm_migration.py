"""stk_0007 confirms every account that existed before email confirmation."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from alembic import command

from stk.migrations import build_alembic_config


class ConfirmExistingUsersTest(unittest.TestCase):
    def test_existing_accounts_count_as_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "db.sqlite"
            config = build_alembic_config(url=f"sqlite:///{path}", quiet=True)
            command.upgrade(config, "stk_0006")
            with sqlite3.connect(path) as db:
                db.execute(
                    "INSERT INTO user (email, password, password_set, active,"
                    " fs_uniquifier, created_at, failed_login_count) VALUES"
                    " ('a@example.com', 'h', 1, 1, 'u', '2026-01-01', 0)"
                )
            command.upgrade(config, "heads")
            with sqlite3.connect(path) as db:
                rows = db.execute("select confirmed_at from user").fetchall()
            self.assertIsNotNone(rows[0][0])
