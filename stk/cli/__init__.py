"""Click commands, grouped by concern. `register_commands` registers everything here."""

from stk.cli.agent import (
    doctor_cmd,
    inspect_cmd,
    new_module,
    report,
    shell,
    smoke,
    verify,
)
from stk.cli.base import console, run_async
from stk.cli.database import (
    create_db,
    db,
)
from stk.cli.users import (
    add_role,
    browser_token,
    cleanup_sessions,
    create,
    install,
    reset,
)

__all__ = [
    "add_role",
    "browser_token",
    "cleanup_sessions",
    "console",
    "create",
    "create_db",
    "db",
    "doctor_cmd",
    "inspect_cmd",
    "install",
    "new_module",
    "report",
    "reset",
    "run_async",
    "shell",
    "smoke",
    "verify",
]
