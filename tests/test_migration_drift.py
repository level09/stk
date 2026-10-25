"""`stk db check` must notice a model that no migration has caught up with."""

import json
import subprocess
import sys
import unittest

# stk's own lineage against stk's own models, on a throwaway SQLite database. A
# fresh interpreter: other tests load the example app, whose tables would join
# the metadata this process shares.
SCRIPT = """
import json, sys
from sqlalchemy import Column, Integer, String, Table
from stk.cli.database import build_migration_drift_report
from stk.extensions import Base
from stk.migrations import get_target_metadata

get_target_metadata()
if sys.argv[1] == "probe":
    Table(
        "drift_probe",
        Base.metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(50)),
    )
url = "sqlite+aiosqlite:///unused.db"
print(json.dumps(build_migration_drift_report(database_url=url)))
"""


def drift(mode):
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, mode],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


class MigrationDriftTest(unittest.TestCase):
    def test_reports_no_drift_for_current_models(self):
        self.assertEqual(drift("models"), [])

    def test_reports_a_model_without_a_migration(self):
        self.assertEqual(drift("probe"), ["add_table: drift_probe"])


if __name__ == "__main__":
    unittest.main()
