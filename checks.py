#!/usr/bin/env python
"""
Quick sanity checks - run before deploying.
No frameworks, no mocking, just real code paths.

Usage:
    uv run python checks.py
    uv run python checks.py -v  # verbose
"""

import asyncio
import sys

VERBOSE = "-v" in sys.argv
PASSED = 0
FAILED = 0


def check(name):
    """Decorator to register a check"""

    def decorator(f):
        async def wrapper(app):
            global PASSED, FAILED
            try:
                result = f(app)
                if asyncio.iscoroutine(result):
                    await result
                PASSED += 1
                print(f"  \033[32m✓\033[0m {name}")
                return True
            except Exception as e:
                FAILED += 1
                print(f"  \033[31m✗\033[0m {name}")
                if VERBOSE:
                    print(f"    → {e}")
                return False

        wrapper._check_name = name
        return wrapper

    return decorator


# =============================================================================
# CHECKS
# =============================================================================


@check("App boots without errors")
def check_app_boots(app):
    assert app is not None
    assert app.config["SECRET_KEY"]


@check("Database connection works")
async def check_database(app):
    import stk.extensions as ext

    async with ext.engine.connect() as conn:
        from sqlalchemy import text

        await conn.execute(text("SELECT 1"))


@check("User model queryable")
async def check_user_model(app):
    from sqlalchemy import select

    import stk.extensions as ext
    from stk.user.models import User

    async with ext.async_session_factory() as session:
        await session.execute(select(User).limit(1))


@check("Role model queryable")
async def check_role_model(app):
    from sqlalchemy import select

    import stk.extensions as ext
    from stk.user.models import Role

    async with ext.async_session_factory() as session:
        await session.execute(select(Role).limit(1))


@check("All blueprints register")
def check_blueprints(app):
    blueprints = list(app.blueprints.keys())
    required = ["users", "public", "portal", "security", "ws"]
    for bp in required:
        assert bp in blueprints, f"Missing blueprint: {bp}"


@check("Critical routes exist")
def check_routes(app):
    rules = [r.rule for r in app.url_map.iter_rules()]

    critical_routes = [
        "/",
        "/login",
        "/dashboard/",
        "/ws",
        "/health",
    ]
    for route in critical_routes:
        assert route in rules, f"Missing route: {route}"


@check("Security config is sane")
def check_security_config(app):
    assert app.config["SECURITY_PASSWORD_LENGTH_MIN"] >= 8


@check("Async session factory initialized")
def check_session_factory(app):
    import stk.extensions as ext

    assert ext.engine is not None, "Engine not initialized"
    assert ext.async_session_factory is not None, "Session factory not initialized"


@check("All models queryable")
async def check_all_models(app):
    from sqlalchemy import select

    import stk.extensions as ext
    from stk.user.models import Activity, OAuth, Session, WebAuthn

    async with ext.async_session_factory() as session:
        for model in [Activity, Session, OAuth, WebAuthn]:
            await session.execute(select(model).limit(1))


@check("Admin routes exist")
def check_admin_routes(app):
    rules = [r.rule for r in app.url_map.iter_rules()]
    admin_routes = [
        "/users/",
        "/roles/",
        "/activities/",
        "/api/users",
        "/api/roles",
        "/api/activities",
    ]
    for route in admin_routes:
        assert route in rules, f"Missing admin route: {route}"


@check("Auth routes exist")
def check_auth_routes(app):
    rules = [r.rule for r in app.url_map.iter_rules()]
    auth_routes = ["/login", "/register", "/logout", "/change"]
    for route in auth_routes:
        assert route in rules, f"Missing auth route: {route}"


@check("WebAuthn enabled")
def check_webauthn(app):
    assert app.config.get("SECURITY_WEBAUTHN") is True
    assert app.config.get("SECURITY_WAN_ALLOW_AS_FIRST_FACTOR") is True


@check("2FA enabled")
def check_two_factor(app):
    assert app.config.get("SECURITY_TWO_FACTOR") is True
    assert "authenticator" in app.config.get("SECURITY_TWO_FACTOR_ENABLED_METHODS", [])


@check("Background tasks module loads")
def check_tasks_module(app):
    from stk.tasks import run_in_background

    assert callable(run_in_background)


@check("WebSocket module loads")
def check_websocket_module(app):
    from stk.websocket import broadcast, get_connected_users

    assert callable(broadcast)
    assert callable(get_connected_users)


@check("No Celery dependency")
def check_no_celery(app):
    import importlib.util

    assert importlib.util.find_spec("celery") is None, "Celery should not be installed"


@check("Templates exist")
def check_templates(app):
    import os

    template_dir = os.path.join(app.root_path, "templates")
    required = [
        "layout.html",
        "dashboard.html",
        "index.html",
        "401.html",
        "404.html",
        "500.html",
        "cms/users.html",
        "cms/roles.html",
        "cms/activities.html",
    ]
    for tpl in required:
        path = os.path.join(template_dir, tpl)
        assert os.path.exists(path), f"Missing template: {tpl}"


@check("Static assets exist")
def check_static_assets(app):
    import os

    static_dir = os.path.join(app.root_path, "static")
    required = [
        "js/vue.min.js",
        "js/vuetify.min.js",
        "js/config.js",
        "js/navigation.js",
        "js/components/index.js",
        "css/vuetify.min.css",
        "css/layout.css",
        "css/app.css",
    ]
    for asset in required:
        path = os.path.join(static_dir, asset)
        assert os.path.exists(path), f"Missing static asset: {asset}"


@check("GET /health returns 200")
async def check_health_endpoint(app):
    client = app.test_client()
    response = await client.get("/health")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = await response.get_json()
    assert data["status"] == "ok", f"Health status: {data['status']}"
    assert data["checks"]["database"] == "ok"


@check("User model has lockout fields")
def check_lockout_fields(app):
    from stk.user.models import User

    assert hasattr(User, "failed_login_count"), "Missing failed_login_count"
    assert hasattr(User, "locked_until"), "Missing locked_until"


@check("Admin password reset route exists")
def check_admin_reset_route(app):
    rules = [r.rule for r in app.url_map.iter_rules()]
    assert "/api/user/<int:id>/reset-password" in rules, (
        "Missing admin reset-password route"
    )


@check("GET / returns 200")
async def check_http_index(app):
    client = app.test_client()
    response = await client.get("/")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"


@check("GET /dashboard/ requires auth")
async def check_auth_redirect(app):
    client = app.test_client()
    response = await client.get("/dashboard/")
    assert response.status_code in (302, 401), (
        f"Expected 302/401, got {response.status_code}"
    )


@check("GET /api/users requires auth")
async def check_api_requires_auth(app):
    client = app.test_client()
    response = await client.get("/api/users")
    assert response.status_code in (302, 401), (
        f"Expected 302/401, got {response.status_code}"
    )


@check("Reported route auth matches real requests")
async def check_route_auth_is_honest(app):
    """Every route the report calls guarded must actually reject anonymous access.

    Agents read `quart inspect routes` to decide what is exposed, so a route
    claiming protection it does not have is the expensive direction of wrong.
    """
    from stk.cli.reports import build_routes_report

    client = app.test_client()
    liars = []
    for route in build_routes_report(app):
        if not route["auth"]["required"] or "GET" not in route["methods"]:
            continue
        if route["arguments"] or route["endpoint"].endswith(".static"):
            continue
        response = await client.get(route["rule"])
        location = response.headers.get("Location", "")
        denied = response.status_code in (401, 403) or (
            response.status_code in (301, 302) and "/login" in location
        )
        if not denied:
            liars.append(f"{route['rule']} -> HTTP {response.status_code}")

    assert not liars, "Routes reported as guarded but reachable: " + ", ".join(liars)


@check("CLI commands registered")
def check_cli_commands(app):
    commands = list(app.cli.commands.keys())
    required = [
        "create-db",
        "install",
        "create",
        "add-role",
        "reset",
        "db",
        "shell",
    ]
    for cmd in required:
        assert cmd in commands, f"Missing CLI command: {cmd}"


@check("Docs name only real commands, flags, and settings")
def check_docs_match_code(app):
    # Docs, skills, and agent context drift silently: a renamed flag or an invented
    # setting reads fine until someone runs it. Every `stk ...` line inside code
    # and every SECURITY_*/STK_* key must resolve against the code.
    import re
    import shlex
    from pathlib import Path

    import click
    import quart_security

    from stk.cli.main import main

    root = Path(__file__).parent
    pages = [
        root / "README.md",
        root / "CLAUDE.md",
        root / "SECURITY.md",
        *root.glob(".claude/skills/**/*.md"),
        *root.glob("docs/src/content/docs/*.md*"),
    ]
    sources = [
        *root.glob("stk/**/*.py"),
        root / "docker-compose.yml",
        root / ".env-sample",
        *Path(quart_security.__file__).parent.glob("*.py"),
    ]
    known_settings = "\n".join(p.read_text() for p in sources)
    commands = {**main.commands, **app.cli.commands}
    help_opts = {"-h", "--help"}

    def resolve(tokens):
        command = None
        for token in tokens:
            if token.startswith("-") and not token[1:].isdigit():
                params = command.params if command else main.params
                opts = {o for p in params for o in p.opts + p.secondary_opts}
                if token.split("=")[0] not in opts | help_opts:
                    return f"unknown option {token}"
            elif command is None or isinstance(command, click.Group):
                children = commands if command is None else command.commands
                if token not in children:
                    return f"unknown command {token}"
                command = children[token]
        return None

    code = re.compile(r"```[^\n]*\n(.*?)```|`([^`\n]+)`", re.S)
    invocation = re.compile(r"^(?:\$\s*)?(?:uv run\s+)?stk\s+(.+)$")
    problems = []
    for page in pages:
        text = page.read_text()
        name = page.relative_to(root)
        for block in code.finditer(text):
            for line in (block.group(1) or block.group(2)).splitlines():
                for segment in re.split(r"&&|\|\||[|;]", line.split(" #")[0]):
                    match = invocation.match(segment.strip())
                    if not match:
                        continue
                    try:
                        tokens = shlex.split(match.group(1))
                    except ValueError:
                        tokens = match.group(1).split()
                    if error := resolve(tokens):
                        problems.append(f"{name}: `stk {match.group(1)}` {error}")
        for key in sorted(set(re.findall(r"\b(?:SECURITY|STK)_[A-Z0-9_]+\b", text))):
            if key not in known_settings:
                problems.append(f"{name}: setting {key} is not read anywhere")

    assert not problems, "Docs drifted from code:\n    " + "\n    ".join(problems)


@check("Docs are one source: indexed, generated, and pointing at real files")
def check_docs_single_source(app):
    # Agents read AGENTS.md first and follow its pointers into docs/, so a page the
    # index misses is invisible, and a pointer to a moved file sends them nowhere.
    import re
    from pathlib import Path

    from click.testing import CliRunner

    from stk.cli.main import main

    root = Path(__file__).parent
    docs = root / "docs/src/content/docs"
    index = (root / "CLAUDE.md").read_text()
    problems = [
        f"CLAUDE.md does not index {page.relative_to(root)}"
        for page in sorted(docs.glob("*.md"))
        if str(page.relative_to(root)) not in index
    ]

    readers = [
        root / "CLAUDE.md",
        root / "README.md",
        *root.glob(".claude/skills/**/*.md"),
    ]
    readers += [*docs.glob("*.md*")]
    path_like = re.compile(
        r"`([\w.-]+(?:/[\w.-]+)+\.(?:md|mdx|py|js|html|css|txt|sh|webp))`"
    )
    for page in readers:
        for path in path_like.findall(page.read_text()):
            if not (root / path).exists():
                problems.append(f"{page.relative_to(root)} points at missing {path}")

    reference = docs / "cli.md"
    generated = CliRunner().invoke(main, ["inspect", "commands", "--markdown"])
    assert generated.exit_code == 0, generated.output
    if reference.read_text() != generated.output:
        problems.append(
            f"{reference.relative_to(root)} is stale"
            " → uv run stk inspect commands --markdown > docs/src/content/docs/cli.md"
        )

    settings = (root / "stk/settings.py").read_text()
    configuration = (docs / "configuration.md").read_text()
    for name in sorted(set(re.findall(r'environ\.get\(\s*"([A-Z0-9_]+)"', settings))):
        if f"`{name}`" not in configuration:
            problems.append(
                f"configuration.md does not list {name}, read in stk/settings.py"
            )

    assert not problems, "Docs are out of sync:\n    " + "\n    ".join(problems)


@check("Repository publishes nothing private")
def check_repo_is_publishable(app):
    # The repo is public and cloned as a template: a committed security review,
    # database, or machine path leaks the moment it is pushed, and history keeps it.
    import re
    import subprocess
    from pathlib import Path

    root = Path(__file__).parent
    if not (root / ".git").exists():
        return
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True, text=True
    ).stdout.split("\0")
    private_path = re.compile(
        r"(^|/)(security-review[^/]*|\.env|instance/.*|.*\.sqlite3?|.*\.db|.*\.pem|.*\.key)$"
    )
    private_text = re.compile(
        r"/(?:Users|home)/[a-z][\w.-]*/|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    )
    problems = [
        f"{path}: private file" for path in tracked if private_path.search(path)
    ]
    for path in tracked:
        file = root / path
        if not path or not file.is_file() or file.is_symlink():
            continue
        try:
            text = file.read_text()
        except UnicodeDecodeError:
            continue
        if match := private_text.search(text):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"{path}:{line}: {match.group(0)}")

    assert not problems, "Private content is tracked:\n    " + "\n    ".join(problems)


# =============================================================================
# RUNNER
# =============================================================================


async def run_checks():
    from stk.app import create_app

    print("\n\033[1mRunning checks...\033[0m\n")

    app = create_app()
    checks = [v for v in globals().values() if hasattr(v, "_check_name")]

    async with app.test_app():
        for check_fn in checks:
            await check_fn(app)

    print()
    if FAILED == 0:
        print(f"\033[32m\033[1m✓ All {PASSED} checks passed\033[0m\n")
        return 0
    else:
        print(f"\033[31m\033[1m✗ {FAILED}/{PASSED + FAILED} checks failed\033[0m\n")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(run_checks()))
