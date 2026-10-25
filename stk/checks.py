#!/usr/bin/env python
"""
Quick sanity checks against the app found from `[tool.stk]` - run before deploying.
No frameworks, no mocking, just real code paths. Checks marked `repo_only` guard
stk's own docs and run only inside the stk repository.

Usage:
    uv run python -m stk.checks
    uv run python -m stk.checks -v  # verbose
"""

import asyncio
import sys

from stk.cli.base import project_root

VERBOSE = "-v" in sys.argv
PASSED = 0
FAILED = 0
ROOT = project_root()
# stk's own checkout: its docs, skills, and generated reference are checked too.
IN_STK_REPO = (ROOT / "stk" / "__init__.py").is_file() and (
    ROOT / "docs/src/content/docs"
).is_dir()


def check(name, repo_only=False):
    """Decorator to register a check"""

    def decorator(f):
        async def wrapper(app):
            if repo_only and not IN_STK_REPO:
                return True
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
        app.jinja_env.get_template(tpl)


@check("Vue interpolations contain no braces")
def check_vue_delimiters(app):
    # The `${ }` delimiter ends at the first `}`, so `${ (x || {}).y }` compiles to
    # a broken render function and the page stays blank with one console error.
    import re

    hazard = re.compile(r"\$\{[^}]*\{")
    # Script bodies hold JS template literals, where `${ {...} }` is valid; blank them
    # but keep their newlines so reported line numbers still match the file.
    script = re.compile(r"(<script\b[^>]*>)(.*?)(</script>)", re.S | re.I)
    import os

    problems = []
    pages = {path for folder in app.template_folders for path in folder.rglob("*.html")}
    for path in sorted(pages):
        text = script.sub(
            lambda m: m.group(1) + "\n" * m.group(2).count("\n") + m.group(3),
            path.read_text(),
        )
        for match in hazard.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"{os.path.relpath(path)}:{line}")

    assert not problems, (
        "`{` inside `${ }` (move it into a method):\n    " + "\n    ".join(problems)
    )


@check("Static assets exist")
def check_static_assets(app):
    required = [
        "js/vue.min.js",
        "js/vuetify.min.js",
        "js/config.js",
        "js/components/index.js",
        "css/vuetify.min.css",
        "css/layout.css",
        "css/app.css",
    ]
    for asset in required:
        assert app.static_file(asset), f"Missing static asset: {asset}"


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


@check("GET / answers 200, after any redirects")
async def check_http_index(app):
    # An app may send / to its sign-in or home page; what it lands on must work.
    client = app.test_client()
    response = await client.get("/", follow_redirects=True)
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
    from stk.cli.main import main

    commands = list(main.commands)
    required = [
        "init",
        "run",
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


@check("Docs name only real commands, flags, and settings", repo_only=True)
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

    root = ROOT
    pages = [
        root / "README.md",
        root / "CLAUDE.md",
        root / "SECURITY.md",
        *root.glob(".claude/skills/**/*.md"),
        *root.glob("docs/src/content/docs/*.md*"),
    ]
    sources = [
        *root.glob("stk/**/*.py"),
        root / "stk/scaffold/app/docker-compose.yml",
        root / "stk/scaffold/app/env-sample",
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


@check(
    "Docs are one source: indexed, generated, and pointing at real files",
    repo_only=True,
)
def check_docs_single_source(app):
    # Agents read AGENTS.md first and follow its pointers into docs/, so a page the
    # index misses is invisible, and a pointer to a moved file sends them nowhere.
    import re

    from click.testing import CliRunner

    from stk.cli.main import main

    root = ROOT
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
    # Docs also name files of an app (`myapp/...`, from the app template), app
    # overrides of core files, and core templates by their `stk/` namespace.
    scaffold = root / "stk/scaffold/app"

    def resolves(path):
        app_path = path.removeprefix("myapp/")
        return any(
            candidate.exists()
            for candidate in (
                root / path,
                scaffold / path.replace("myapp/", "__app__/", 1),
                root / "stk" / app_path,
                root / "stk/templates" / path.removeprefix("stk/"),
            )
        )

    for page in readers:
        for path in path_like.findall(page.read_text()):
            if not resolves(path):
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

    # Apps get their own CLAUDE.md from the template; its rules must be stk's.
    rules = index[index.index("## Rules that fail silently") :]
    if rules not in (root / "stk/scaffold/app/CLAUDE.md").read_text():
        problems.append(
            "stk/scaffold/app/CLAUDE.md does not carry CLAUDE.md's rules section"
            " → copy it from '## Rules that fail silently' to the end"
        )

    # Agents load these whole on every task; an index past ~8KB stops being read
    # as an index. Move detail into a docs page instead of raising the budget.
    budgets = {root / "CLAUDE.md": 8192, root / "stk/scaffold/app/CLAUDE.md": 8192}
    budgets |= dict.fromkeys(root.glob(".claude/skills/*/SKILL.md"), 4096)
    for page, ceiling in budgets.items():
        if (size := len(page.read_bytes())) > ceiling:
            problems.append(
                f"{page.relative_to(root)} is {size} bytes, over its {ceiling} budget"
                " → move detail into a docs page and link it"
            )

    assert not problems, "Docs are out of sync:\n    " + "\n    ".join(problems)


@check("Migrations do not destroy data")
def check_migrations_are_additive(app):
    # Autogenerate turns a renamed field into drop + add, and SQLite batch mode
    # rebuilds the table, so a lost column reads like a normal diff in review.
    # Mark a deliberate one with a `# destructive: <reason>` comment in upgrade().
    import ast

    from stk.migrations import CORE_VERSIONS, app_versions

    destructive = {"drop_table", "drop_column", "rename_table"}
    problems = []
    for path in sorted([*CORE_VERSIONS.glob("*.py"), *app_versions(app).glob("*.py")]):
        source = path.read_text()
        for func in ast.parse(source).body:
            if not (isinstance(func, ast.FunctionDef) and func.name == "upgrade"):
                continue
            if "# destructive:" in ast.get_source_segment(source, func):
                continue
            for node in ast.walk(func):
                if not (
                    isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                ):
                    continue
                op, kwargs = node.func.attr, {k.arg for k in node.keywords}
                where = f"{path.name}:{node.lineno}"
                if op in destructive:
                    problems.append(f"{where} {op}")
                elif op == "alter_column" and kwargs & {"new_column_name", "type_"}:
                    problems.append(f"{where} alter_column renames or retypes")
                elif op == "add_column":
                    column = next(
                        (a for a in node.args if isinstance(a, ast.Call)), None
                    )
                    flags = {k.arg: k.value for k in column.keywords} if column else {}
                    not_null = getattr(flags.get("nullable"), "value", True) is False
                    if not_null and "server_default" not in flags:
                        problems.append(
                            f"{where} add_column NOT NULL without server_default"
                        )

    assert not problems, (
        "Destructive migration steps (add `# destructive: <reason>` to upgrade()"
        " if intended):\n    " + "\n    ".join(problems)
    )


@check("Repository publishes nothing private")
def check_repo_is_publishable(app):
    # The repo is public and cloned as a template: a committed security review,
    # database, or machine path leaks the moment it is pushed, and history keeps it.
    import re
    import subprocess

    root = ROOT
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
    from stk.cli.base import load_app

    print("\n\033[1mRunning checks...\033[0m\n")

    app = load_app()
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
