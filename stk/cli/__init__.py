"""Click commands, grouped by concern. `stk.cli.main` registers everything here."""

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
from stk.cli.develop import init, run
from stk.cli.users import (
    add_role,
    browser_token,
    cleanup_sessions,
    create,
    install,
    protect_mfa,
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
    "init",
    "inspect_cmd",
    "install",
    "new_module",
    "protect_mfa",
    "report",
    "reset",
    "run",
    "run_async",
    "shell",
    "smoke",
    "verify",
]
