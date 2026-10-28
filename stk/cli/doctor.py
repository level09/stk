"""`stk doctor`: the state of this checkout, and the next action for anything wrong.

Answers the questions you would otherwise discover one failed command at a time:
is the environment configured, is the database migrated, is there an admin, are
the vendored assets present, is the test-only login accidentally exposed.
"""

from pathlib import Path

from sqlalchemy import func, select

import stk
import stk.extensions as ext
from stk.cli.base import app_spec, cli_app, project_root, run_async
from stk.migrations import build_alembic_config, sync_url

CORE_STATIC = Path(stk.__file__).parent / "static"

OK = "ok"
WARN = "warn"
FAIL = "fail"


def _finding(name, status, detail, remedy=None):
    return {"name": name, "status": status, "detail": detail, "remedy": remedy}


def _check_env_file(root):
    path = root / ".env"
    if not path.exists():
        return _finding(
            "env file",
            FAIL,
            ".env is missing",
            "copy .env-sample to .env, fill secrets",
        )
    return _finding("env file", OK, str(path.relative_to(root)))


def _check_secrets(config):
    weak = [
        name
        for name in ("SECRET_KEY", "SECURITY_PASSWORD_SALT")
        if len(str(config.get(name) or "")) < 32
    ]
    if weak:
        return _finding(
            "secrets",
            FAIL,
            f"weak or missing: {', '.join(weak)}",
            "set 32+ random characters in .env",
        )
    return _finding("secrets", OK, "SECRET_KEY and password salt look random")


def _check_database(config):
    url = config["SQLALCHEMY_DATABASE_URI"]
    if url.startswith("sqlite"):
        path = Path(url.split("///")[-1])
        if not path.exists():
            return _finding(
                "database", FAIL, f"{path} does not exist", "uv run stk create-db"
            )
        size = path.stat().st_size // 1024
        return _finding("database", OK, f"sqlite {path.name} ({size} KiB)")
    return _finding("database", OK, url.split("@")[-1])


def _as_tuple(value):
    return () if value is None else (value,) if isinstance(value, str) else value


def _applied(script, current):
    """Every revision the database already has: its heads and their ancestry.

    The version table holds only heads, and an app revision that depends on
    stk's head stands in for it.
    """
    applied, pending = set(), list(current)
    while pending:
        revision = script.get_revision(pending.pop())
        if revision.revision not in applied:
            applied.add(revision.revision)
            pending += [
                *_as_tuple(revision.down_revision),
                *_as_tuple(revision.dependencies),
            ]
    return applied


def _defined(script, revision):
    try:
        script.get_revision(revision)
    except Exception:  # alembic raises CommandError for a revision it cannot find
        return False
    return True


def _check_migrations(app):
    """Compare the database revisions against the migration heads on disk."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    script = ScriptDirectory.from_config(build_alembic_config(app))
    heads = set(script.get_heads())
    engine = create_engine(sync_url(app.config["SQLALCHEMY_DATABASE_URI"]))
    try:
        with engine.connect() as connection:
            current = set(MigrationContext.configure(connection).get_current_heads())
    except Exception as exc:  # unreachable database is its own diagnosis
        return _finding("migrations", FAIL, str(exc)[:80], "uv run stk db upgrade")
    finally:
        engine.dispose()

    shown = ", ".join(sorted(heads))
    if not current:
        return _finding(
            "migrations", FAIL, "database has no revision", "uv run stk db upgrade"
        )
    unknown = sorted(rev for rev in current if not _defined(script, rev))
    if unknown:
        return _finding(
            "migrations",
            FAIL,
            f"database is stamped at {', '.join(unknown)}, which no migration defines",
            "uv run stk db stamp heads (after checking the schema matches)",
        )
    if missing := sorted(heads - _applied(script, current)):
        return _finding(
            "migrations",
            WARN,
            f"database is behind: {', '.join(missing)} not applied",
            "uv run stk db upgrade",
        )
    return _finding("migrations", OK, f"at heads ({shown})")


def _check_admin():
    from stk.user.models import Role, User

    async def _count():
        async with ext.async_session_factory() as session:
            statement = (
                select(func.count())
                .select_from(User)
                .where(User.roles.any(Role.name == "admin"))
            )
            return (await session.execute(statement)).scalar_one()

    try:
        admins = run_async(_count())
    except Exception as exc:
        return _finding("admin user", FAIL, str(exc)[:80], "uv run stk db upgrade")
    if admins:
        return _finding("admin user", OK, f"{admins} admin(s)")
    return _finding("admin user", WARN, "no admin user", "uv run stk install")


def _check_assets():
    versions = CORE_STATIC / "VERSIONS.txt"
    if not versions.exists():
        return _finding("assets", WARN, "VERSIONS.txt missing", "./vendor.sh")
    expected = [
        CORE_STATIC / name
        for name in (
            "js/vue.min.js",
            "js/vuetify.min.js",
            "css/vuetify.min.css",
            "icons/tabler-icons.min.css",
            "icons/fonts/tabler-icons.core.woff2",
        )
    ]
    missing = [path.name for path in expected if not path.exists()]
    if missing:
        return _finding("assets", FAIL, f"missing: {', '.join(missing)}", "./vendor.sh")
    pinned = " ".join(versions.read_text().split("\n")[0:2]).strip()
    return _finding("assets", OK, pinned)


def _check_agent_login(config):
    enabled = config.get("STK_ENABLE_AGENT_LOGIN", False)
    env = config.get("STK_ENV", "production")
    if enabled and env != "development":
        return _finding(
            "agent login",
            FAIL,
            f"test-only login enabled with STK_ENV={env}",
            "unset STK_ENABLE_AGENT_LOGIN, or set STK_ENV=development",
        )
    return _finding(
        "agent login", OK, "enabled in development only" if enabled else "disabled"
    )


def _check_browser():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return _finding(
            "browser", WARN, "playwright not installed", "uv sync --extra dev"
        )
    try:
        with sync_playwright() as playwright:
            path = Path(playwright.chromium.executable_path)
    except Exception:
        return _finding(
            "browser",
            WARN,
            "chromium not installed",
            "uv run playwright install chromium",
        )
    if not path.exists():
        return _finding(
            "browser",
            WARN,
            "chromium not installed",
            "uv run playwright install chromium",
        )
    return _finding("browser", OK, "chromium ready for stk smoke")


def _check_repl():
    try:
        import ptpython  # noqa: F401
    except ImportError:
        return _finding(
            "shell",
            WARN,
            "ptpython missing, stk shell falls back to the plain console",
            "uv sync --extra dev",
        )
    return _finding("shell", OK, "ptpython: highlighting and completion")


def build_doctor_report():
    """Return every finding, plus the worst status seen."""
    findings = [_check_env_file(project_root())]
    try:
        app = cli_app()
    except Exception as exc:  # an app that cannot load is the diagnosis
        findings.append(
            _finding("app", FAIL, str(exc)[:120], "read the error, then rerun")
        )
        app = None
    if app is not None:
        findings += [
            _finding("app", OK, app_spec()),
            _check_secrets(app.config),
            _check_database(app.config),
            _check_migrations(app),
            _check_admin(),
            _check_agent_login(app.config),
        ]
    findings += [_check_assets(), _check_browser(), _check_repl()]
    if any(item["status"] == FAIL for item in findings):
        status = FAIL
    elif any(item["status"] == WARN for item in findings):
        status = WARN
    else:
        status = OK
    return {"status": status, "findings": findings}
