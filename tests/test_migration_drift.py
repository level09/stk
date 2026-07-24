"""`quart db check` must notice a model that no migration has caught up with."""

import unittest

from sqlalchemy import Column, Integer, String, Table

from stk.cli.database import build_migration_drift_report
from stk.extensions import Base
from stk.migrations import get_target_metadata


class MigrationDriftTest(unittest.TestCase):
    def setUp(self):
        get_target_metadata()

    def test_reports_no_drift_for_current_models(self):
        self.assertEqual(build_migration_drift_report(), [])

    def test_reports_a_model_without_a_migration(self):
        table = Table(
            "drift_probe",
            Base.metadata,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)),
        )
        try:
            drift = build_migration_drift_report()
        finally:
            Base.metadata.remove(table)

        self.assertEqual(drift, ["add_table: drift_probe"])


if __name__ == "__main__":
    unittest.main()
