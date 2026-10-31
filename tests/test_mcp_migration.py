"""stk_0006 moves stk's own `mcp_token` to `stk_mcp_token` and leaves an app's alone."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from alembic import command

from stk.migrations import build_alembic_config

LEGACY_TOKEN = (
    "INSERT INTO mcp_token (id, user_id, name, token_hash, user_uniquifier,"
    " scopes, created_at, expires_at) VALUES (1, 1, 'agent', 'h', 'u', '[]',"
    " '2026-10-31', '2027-01-29')"
)


class McpTokenTableMigrationTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "db.sqlite"
        self.config = build_alembic_config(url=f"sqlite:///{self.path}", quiet=True)

    def tearDown(self):
        self.dir.cleanup()

    def sql(self, statement):
        with sqlite3.connect(self.path) as db:
            return db.execute(statement).fetchall()

    def tables(self):
        return {
            r[0] for r in self.sql("select name from sqlite_master where type='table'")
        }

    def test_fresh_database_gets_only_the_prefixed_table(self):
        command.upgrade(self.config, "heads")
        self.assertIn("stk_mcp_token", self.tables())
        self.assertNotIn("mcp_token", self.tables())

    def test_tokens_from_the_old_table_name_move_over(self):
        # A database that ran stk_0005 from 17.2.0 to 17.2.2.
        command.upgrade(self.config, "stk_0004")
        self.sql(
            "CREATE TABLE mcp_token (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT,"
            " token_hash TEXT, user_uniquifier TEXT, scopes JSON, created_at DATETIME,"
            " expires_at DATETIME, last_used_at DATETIME)"
        )
        self.sql(LEGACY_TOKEN)
        self.sql("UPDATE alembic_version SET version_num = 'stk_0005'")
        command.upgrade(self.config, "heads")
        self.assertNotIn("mcp_token", self.tables())
        self.assertEqual(self.sql("select name from stk_mcp_token"), [("agent",)])

    def test_an_apps_own_mcp_token_table_is_left_alone(self):
        command.upgrade(self.config, "stk_0004")
        self.sql("CREATE TABLE mcp_token (id INTEGER PRIMARY KEY, grant_id TEXT)")
        self.sql("INSERT INTO mcp_token (id, grant_id) VALUES (7, 'g')")
        command.upgrade(self.config, "heads")
        self.assertEqual(self.sql("select id, grant_id from mcp_token"), [(7, "g")])
        self.assertIn("stk_mcp_token", self.tables())
