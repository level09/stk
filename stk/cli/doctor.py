"""`stk doctor`: the state of this checkout, and the next action for anything wrong.

Answers the questions you would otherwise discover one failed command at a time:
is the environment configured, is the database migrated, is there an admin, are
the vendored assets present, is the test-only login accidentally exposed.
"""

from pathlib import Path

from sqlalchemy import func, select

import stk.extensions as ext
from stk.cli.base import run_async
from stk.migrations import PROJECT_ROOT, build_alembic_config, get_database_url

OK = "ok"
WARN = "warn"
FAIL = "fail"


def _finding(name, status, detail, remedy=None):
    return {"name": name, "status": status, "detail": detail, "remedy": remedy}


def _check_env_file():
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return _finding("env file", FAIL, ".env is missing", "./setup.sh")
    return _finding("env file", OK, str(path.relative_to(PROJECT_ROOT)))


def _check_secrets(config):
    weak = [
        name
        for name in ("SECRET_KEY", "SECURITY_PASSWORD_SALT")
        if not getattr(config, name, None) or len(str(getattr(config, name))) < 32
    ]
    if weak:
        return _finding(
            "secrets",
            FAIL,
            f"weak or missing: {', '.join(weak)}",
            "regenerate with ./setup.sh, or set 32+ random characters in .env",
        )
    return _finding("secrets", OK, "SECRET_KEY and password salt look random")


def _check_database(config):
    url = get_database_url()
    if url.startswith("sqlite"):
        path = Path(url.split("///")[-1])
        if not path.exists():
            return _finding(
                "database", FAIL, f"{path} does not exist", "uv run stk create-db"
            )
        size = path.stat().st_size // 1024
        return _finding("database", OK, f"sqlite {path.name} ({size} KiB)")
    return _finding("database", OK, url.split("@")[-1])


def _check_migrations():
    """Compare the database revision against the migration scripts on disk."""
    from alembic.runtime.migration import MigrationContext
    from alembic.script import ScriptDirectory
    from sqlalchemy import create_engine

    script = ScriptDirectory.from_config(build_alembic_config())
    head = script.get_current_head()
    engine = create_engine(get_database_url(sync=True))
    try:
        with engine.connect() as connection:
            current = MigrationContext.configure(connection).get_current_revision()
    except Exception as exc:  # unreachable database is its own diagnosis
        return _finding("migrations", FAIL, str(exc)[:80], "uv run stk create-db")
    finally:
        engine.dispose()

    if current is None:
        return _finding(
            "migrations", FAIL, "database has no revision", "uv run stk db upgrade"
        )
    if current == head:
        return _finding("migrations", OK, f"at head ({head})")
    try:
        script.get_revision(current)
    except Exception:  # alembic raises CommandError for a revision it cannot find
        return _finding(
            "migrations",
            FAIL,
            f"database is stamped at {current}, which no migration defines",
            f"uv run stk db stamp {head} (after checking the schema matches)",
        )
    return _finding(
        "migrations",
        WARN,
        f"database at {current}, head is {head}",
        "uv run stk db upgrade",
    )


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
        return _finding("admin user", FAIL, str(exc)[:80], "uv run stk create-db")
    if admins:
        return _finding("admin user", OK, f"{admins} admin(s)")
    return _finding("admin user", WARN, "no admin user", "uv run stk install")


def _check_assets():
    versions = PROJECT_ROOT / "stk" / "static" / "VERSIONS.txt"
    if not versions.exists():
        return _finding("assets", WARN, "VERSIONS.txt missing", "./vendor.sh")
    expected = [
        PROJECT_ROOT / "stk" / "static" / name
        for name in (
            "js/vue.min.js",
            "js/vuetify.min.js",
            "css/vuetify.min.css",
            "icons/tabler-icons.min.css",
            "icons/fonts/tabler-icons.woff2",
        )
    ]
    missing = [path.name for path in expected if not path.exists()]
    if missing:
        return _finding("assets", FAIL, f"missing: {', '.join(missing)}", "./vendor.sh")
    pinned = " ".join(versions.read_text().split("\n")[0:2]).strip()
    return _finding("assets", OK, pinned)


def _check_agent_login(config):
    enabled = getattr(config, "STK_ENABLE_AGENT_LOGIN", False)
    env = getattr(config, "STK_ENV", "production")
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
    from stk.settings import Config

    findings = [
        _check_env_file(),
        _check_secrets(Config),
        _check_database(Config),
        _check_migrations(),
        _check_admin(),
        _check_assets(),
        _check_agent_login(Config),
        _check_browser(),
        _check_repl(),
    ]
    if any(item["status"] == FAIL for item in findings):
        status = FAIL
    elif any(item["status"] == WARN for item in findings):
        status = WARN
    else:
        status = OK
    return {"status": status, "findings": findings}
