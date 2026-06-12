"""Click commands."""

import asyncio
import html
import inspect as pyinspect
import json
import os
import secrets
import socket
import string
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import click
import httpx
from quart_security import hash_password
from rich.console import Console
from sqlalchemy import select

import stk.extensions as ext
from alembic import command
from stk.agent_login import create_agent_login_token
from stk.migrations import build_alembic_config
from stk.user.models import User

console = Console()


VERIFY_COMMANDS = [
    ("ruff", ["ruff", "check", "."]),
    ("checks", [sys.executable, "checks.py"]),
    ("migration-current", [sys.executable, "-m", "quart", "db", "current"]),
]
SMOKE_EMAIL = "smoke@example.com"
SMOKE_PASSWORD = "SmokePassword123!"
SMOKE_SCREENSHOT = Path(".stk/smoke/dashboard.png")


def run_async(coro):
    """Run an async function in sync context (for CLI commands)."""

    async def _wrapper():
        try:
            return await coro
        finally:
            if ext.engine:
                await ext.engine.dispose()

    return asyncio.run(_wrapper())


def _command_runner(command):
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        if command[0] == "ruff":
            return None, "", "ruff not installed"
        raise
    return result.returncode, result.stdout, result.stderr


def _route_source(view_func):
    if view_func is None:
        return None
    source_file = pyinspect.getsourcefile(view_func)
    if source_file is None:
        return None
    try:
        _, line = pyinspect.getsourcelines(view_func)
    except OSError:
        line = None
    source = {"file": str(Path(source_file).resolve())}
    if line is not None:
        source["line"] = line
    return source


def _route_auth(rule):
    if rule.rule.startswith("/_test/"):
        return {"required": False, "source": "test-only", "scheme": "agent-token"}
    blueprint = rule.endpoint.rsplit(".", 1)[0] if "." in rule.endpoint else None
    if blueprint in {"portal", "users"}:
        return {"required": True, "source": "blueprint", "scheme": "session"}
    if rule.rule.startswith("/api/") or rule.rule in {"/dashboard/"}:
        return {"required": True, "source": "route", "scheme": "session"}
    if rule.rule in {"/login", "/register", "/reset", "/confirm"}:
        return {"required": False, "source": "security", "scheme": "public"}
    return {"required": False, "source": "default", "scheme": "public"}


def build_routes_report(app):
    """Return machine-readable route facts for agents and tooling."""
    routes = []
    for rule in sorted(app.url_map.iter_rules(), key=lambda item: item.rule):
        methods = sorted((rule.methods or set()) - {"HEAD", "OPTIONS"})
        view_func = app.view_functions.get(rule.endpoint)
        blueprint = rule.endpoint.rsplit(".", 1)[0] if "." in rule.endpoint else None
        routes.append(
            {
                "rule": rule.rule,
                "endpoint": rule.endpoint,
                "blueprint": blueprint,
                "methods": methods,
                "arguments": sorted(rule.arguments),
                "auth": _route_auth(rule),
                "source": _route_source(view_func),
            }
        )
    return routes


def build_verify_report(commands=None, runner=_command_runner):
    """Run verification commands and return a compact report."""
    checks = []
    for name, command_args in commands or VERIFY_COMMANDS:
        returncode, stdout, stderr = runner(command_args)
        checks.append(
            {
                "name": name,
                "command": command_args,
                "returncode": returncode,
                "status": "skipped"
                if returncode is None
                else "passed"
                if returncode == 0
                else "failed",
                "stdout": stdout.strip(),
                "stderr": stderr.strip(),
            }
        )
    status = (
        "passed"
        if all(check["returncode"] in (0, None) for check in checks)
        else "failed"
    )
    return {"status": status, "checks": checks}


def build_smoke_report(pages, dashboard_screenshot):
    """Return a browser smoke report with per-page failure reasons."""
    page_reports = []
    for page in pages:
        problems = []
        status_code = page.get("status")
        if status_code is None:
            problems.append("no document response")
        elif status_code >= 400:
            problems.append(f"HTTP {status_code}")

        for entry in page.get("console", []):
            if entry["type"] == "error":
                problems.append(f"console error: {entry['text']}")

        for request in page.get("failed_requests", []):
            failure = request.get("failure") or "unknown"
            problems.append(f"request failed: {request['url']} {failure}")

        page_reports.append(
            {
                "name": page["name"],
                "path": page["path"],
                "status_code": status_code,
                "status": "failed" if problems else "passed",
                "console": page.get("console", []),
                "failed_requests": page.get("failed_requests", []),
                "problems": problems,
            }
        )

    status = (
        "passed"
        if all(page["status"] == "passed" for page in page_reports)
        else "failed"
    )
    return {
        "status": status,
        "dashboard_screenshot": str(dashboard_screenshot),
        "pages": page_reports,
    }


def smoke_exit_code(report):
    return 0 if report["status"] == "passed" else 1


def _free_localhost_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _smoke_env(database_path):
    env = os.environ.copy()
    env.update(
        {
            "QUART_APP": "run:app",
            "SECRET_KEY": secrets.token_urlsafe(32),
            "SECURITY_PASSWORD_SALT": secrets.token_urlsafe(32),
            "SQLALCHEMY_DATABASE_URI": f"sqlite+aiosqlite:///{database_path}",
            "STK_ENV": "development",
            "STK_ENABLE_AGENT_LOGIN": "true",
            "SESSION_COOKIE_SECURE": "False",
        }
    )
    env.pop("REDIS_URL", None)
    env.pop("REDIS_SESSION", None)
    return env


def _run_smoke_setup(env):
    commands = [
        [sys.executable, "-m", "quart", "--app", "run:app", "db", "upgrade"],
        [
            sys.executable,
            "-m",
            "quart",
            "--app",
            "run:app",
            "install",
            "--email",
            SMOKE_EMAIL,
            "--password",
            SMOKE_PASSWORD,
        ],
    ]
    for command_args in commands:
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            raise click.ClickException(
                "smoke setup failed for "
                f"{' '.join(command_args)}\n{result.stderr.strip()}"
            )


def _create_smoke_token(database_uri, secret_key, password_salt):
    from stk.app import create_app
    from stk.settings import Config

    class SmokeConfig(Config):
        SECRET_KEY = secret_key
        SECURITY_PASSWORD_SALT = password_salt
        SQLALCHEMY_DATABASE_URI = database_uri
        SESSION_TYPE = None
        STK_ENV = "development"
        STK_ENABLE_AGENT_LOGIN = True

    async def _create_token():
        app = create_app(SmokeConfig)
        async with app.app_context():
            return create_agent_login_token(SMOKE_EMAIL, "/dashboard/")

    return run_async(_create_token())


def _start_smoke_server(port, env):
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "quart",
            "--app",
            "run:app",
            "run",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _wait_for_smoke_server(base_url, process):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout, stderr = process.communicate(timeout=1)
            raise click.ClickException(
                "smoke server exited before accepting requests\n"
                f"{stdout.strip()}\n{stderr.strip()}"
            )
        try:
            response = httpx.get(f"{base_url}/login", timeout=1)
            if response.status_code < 500:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise click.ClickException("smoke server did not start within 20 seconds")


def _stop_smoke_server(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate(timeout=5)


async def _visit_smoke_page(context, base_url, name, path, screenshot_path=None):
    page = await context.new_page()
    console_entries = []
    failed_requests = []

    def _record_console(message):
        if message.type in {"error", "warning"}:
            console_entries.append({"type": message.type, "text": message.text})

    def _record_failed_request(request):
        failure = request.failure
        if callable(failure):
            failure = failure()
        failed_requests.append({"url": request.url, "failure": failure or ""})

    page.on("console", _record_console)
    page.on("requestfailed", _record_failed_request)
    response = await page.goto(f"{base_url}{path}", wait_until="networkidle")
    if screenshot_path is not None:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(screenshot_path), full_page=True)
    await page.close()
    return {
        "name": name,
        "path": path,
        "status": response.status if response else None,
        "console": console_entries,
        "failed_requests": failed_requests,
    }


async def _run_playwright_smoke(base_url, token):
    try:
        from playwright.async_api import Error as PlaywrightError
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise click.ClickException(
            "Playwright is not installed. Run `uv sync --extra dev`."
        ) from exc

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            context = await browser.new_context()
            pages = [
                await _visit_smoke_page(context, base_url, "login", "/login"),
                await _visit_smoke_page(
                    context,
                    base_url,
                    "agent-login",
                    f"/_test/login?token={token}",
                ),
                await _visit_smoke_page(
                    context,
                    base_url,
                    "dashboard",
                    "/dashboard/",
                    SMOKE_SCREENSHOT,
                ),
                await _visit_smoke_page(context, base_url, "admin-users", "/users/"),
            ]
            await context.close()
            await browser.close()
    except PlaywrightError as exc:
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message:
            raise click.ClickException(
                "Chromium is not installed. Run `uv run playwright install chromium`."
            ) from exc
        raise

    pages[1]["path"] = "/_test/login?token=<redacted>"
    return build_smoke_report(pages, SMOKE_SCREENSHOT)


def _print_smoke_report(report):
    click.echo(f"Smoke status: {report['status']}")
    click.echo(f"Dashboard screenshot: {report['dashboard_screenshot']}")
    for page in report["pages"]:
        click.echo(f"{page['status'].upper()} {page['name']} {page['path']}")
        click.echo(f"  HTTP: {page['status_code']}")
        for entry in page["console"]:
            click.echo(f"  console {entry['type']}: {entry['text']}")
        for request in page["failed_requests"]:
            click.echo(
                f"  request failed: {request['url']} {request.get('failure') or ''}"
            )
        for problem in page["problems"]:
            click.echo(f"  problem: {problem}")


def build_project_report_html(routes, verify_report):
    """Render a static project review artifact."""
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(route['rule'])}</td>"
        f"<td>{html.escape(', '.join(route['methods']))}</td>"
        f"<td>{html.escape(str(route['blueprint']))}</td>"
        f"<td>{html.escape(route['auth']['scheme'])}</td>"
        f"<td>{html.escape(route['auth']['source'])}</td>"
        "</tr>"
        for route in routes
    )
    check_rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(check['name'])}</td>"
        f"<td>{html.escape(check['status'])}</td>"
        f"<td>{html.escape(' '.join(check['command']))}</td>"
        "</tr>"
        for check in verify_report["checks"]
    )
    status = html.escape(verify_report["status"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>STK Project Report</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; color: #1f2933; }}
    h1 {{ font-size: 28px; margin-bottom: 8px; }}
    h2 {{ font-size: 18px; margin-top: 28px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #d8dee4; padding: 8px; text-align: left; }}
    th {{ background: #f6f8fa; }}
    .status {{ display: inline-block; padding: 4px 8px; border: 1px solid #d8dee4; }}
  </style>
</head>
<body>
  <h1>STK Project Report</h1>
  <p>Generated route and verification artifact for reviewing project boundaries.</p>
  <p>Verification status: <span class="status">{status}</span></p>
  <h2>Routes</h2>
  <table>
    <thead>
      <tr><th>Route</th><th>Methods</th><th>Blueprint</th><th>Auth</th><th>Source</th></tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
  <h2>Verification</h2>
  <table>
    <thead>
      <tr><th>Check</th><th>Status</th><th>Command</th></tr>
    </thead>
    <tbody>{check_rows}</tbody>
  </table>
</body>
</html>
"""


@click.command()
def create_db():
    """Apply all database migrations."""
    import os

    from stk.settings import Config

    instance_dir = os.path.join(Config.PROJECT_ROOT, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    command.upgrade(build_alembic_config(), "head")
    console.print("[green]Database migrations applied successfully[/]")


@click.group("browser-token")
def browser_token():
    """Create test-only browser login URLs."""


@browser_token.command("create")
@click.option("--user", "email", required=True, help="Test user email.")
@click.option("--ttl", default=60, type=int, help="Token TTL in seconds.")
@click.option("--next", "next_path", default="/dashboard/", help="Local redirect path.")
def browser_token_create(email, ttl, next_path):
    """Create a signed test-only browser login URL."""
    from stk.app import create_app

    app = create_app()
    if ttl > app.config["STK_AGENT_LOGIN_MAX_TTL_SECONDS"]:
        raise click.ClickException("ttl exceeds STK_AGENT_LOGIN_MAX_TTL_SECONDS")
    if not app.config["STK_ENABLE_AGENT_LOGIN"]:
        raise click.ClickException("agent login is disabled")

    async def _create_token():
        async with app.app_context():
            return create_agent_login_token(email, next_path)

    token = run_async(_create_token())
    click.echo(f"/_test/login?token={token}")


@click.group(name="inspect")
def inspect_cmd():
    """Inspect app structure for agents and tooling."""


@inspect_cmd.command("routes")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def inspect_routes(as_json):
    """Inspect registered routes."""
    from stk.app import create_app

    report = build_routes_report(create_app())
    if as_json:
        click.echo(json.dumps(report, indent=2))
        return

    for route in report:
        methods = ",".join(route["methods"])
        click.echo(f"{methods:12} {route['rule']} -> {route['endpoint']}")


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def verify(as_json):
    """Run STK verification checks."""
    report = build_verify_report()
    if as_json:
        click.echo(json.dumps(report, indent=2))
        raise click.exceptions.Exit(0 if report["status"] == "passed" else 1)

    for check in report["checks"]:
        marker = "✓" if check["status"] == "passed" else "✗"
        click.echo(f"{marker} {check['name']}")
    raise click.exceptions.Exit(0 if report["status"] == "passed" else 1)


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def smoke(as_json):
    """Run a real-browser smoke check against a temporary development app."""
    with tempfile.TemporaryDirectory(prefix="stk-smoke-") as temp_dir:
        database_path = Path(temp_dir) / "smoke.db"
        env = _smoke_env(database_path)
        _run_smoke_setup(env)

        token = _create_smoke_token(
            env["SQLALCHEMY_DATABASE_URI"],
            env["SECRET_KEY"],
            env["SECURITY_PASSWORD_SALT"],
        )
        port = _free_localhost_port()
        base_url = f"http://127.0.0.1:{port}"
        server = _start_smoke_server(port, env)
        try:
            _wait_for_smoke_server(base_url, server)
            report = asyncio.run(_run_playwright_smoke(base_url, token))
        finally:
            _stop_smoke_server(server)

    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        _print_smoke_report(report)
    raise click.exceptions.Exit(smoke_exit_code(report))


@click.command()
@click.option(
    "-o",
    "--output",
    default="docs/stk-report.html",
    help="HTML output path.",
)
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def report(output, as_json):
    """Generate a static project report."""
    from stk.app import create_app

    routes = build_routes_report(create_app())
    verify_report = build_verify_report()
    report_data = {"routes": routes, "verification": verify_report}
    if as_json:
        click.echo(json.dumps(report_data, indent=2))
        return

    html_report = build_project_report_html(routes, verify_report)
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_report)
    console.print(f"[green]Project report written:[/] {output_path}")


@click.group()
def db():
    """Alembic-backed database migration commands."""


@db.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision):
    """Upgrade the database to a target revision."""
    command.upgrade(build_alembic_config(), revision)


@db.command("downgrade")
@click.argument("revision")
def db_downgrade(revision):
    """Downgrade the database to a target revision."""
    command.downgrade(build_alembic_config(), revision)


@db.command("revision")
@click.option("-m", "--message", required=True, help="Revision message")
@click.option(
    "--autogenerate/--empty",
    default=True,
    help="Autogenerate from model metadata or create an empty revision",
)
def db_revision(message, autogenerate):
    """Create a new migration revision."""
    command.revision(
        build_alembic_config(),
        message=message,
        autogenerate=autogenerate,
    )


@db.command("current")
def db_current():
    """Show the current database revision."""
    command.current(build_alembic_config())


@db.command("history")
def db_history():
    """Show migration history."""
    command.history(build_alembic_config())


@db.command("stamp")
@click.argument("revision", default="head")
def db_stamp(revision):
    """Stamp a database with a revision without running migrations."""
    command.stamp(build_alembic_config(), revision)


@click.command()
@click.option("-e", "--email", default=None, help="Admin email")
@click.option("-p", "--password", default=None, help="Admin password")
def install(email, password):
    """Install a default admin user and add an admin role to it."""

    async def _run():
        from stk.user.models import Role

        async with ext.async_session_factory() as session:
            admin_role = (
                await session.execute(select(Role).where(Role.name == "admin"))
            ).scalar_one_or_none()
            if not admin_role:
                admin_role = Role(name="admin")
                session.add(admin_role)
                await session.commit()

            admin_user = (
                await session.execute(
                    select(User).where(User.roles.any(Role.name == "admin"))
                )
            ).scalar_one_or_none()
            if admin_user:
                console.print(
                    f"[yellow]An admin user already exists:[/] [blue]{admin_user.email}[/]"
                )
                return

            nonlocal email, password
            if not email:
                email = click.prompt("Admin email", default="admin@example.com")

            generated = False
            if not password:
                password = "".join(
                    secrets.choice(string.ascii_letters + string.digits + "@#$%^&*")
                    for _ in range(32)
                )
                generated = True

            user = User(
                email=email,
                name="Super Admin",
                password=hash_password(password),
                active=True,
                confirmed_at=datetime.now(),
            )
            user.roles.append(admin_role)
            session.add(user)
            await session.commit()

            console.print("\n[green]✓[/] Admin user created successfully!")
            console.print(f"[blue]Email:[/] {email}")
            if generated:
                console.print(f"[blue]Password:[/] [red]{password}[/]")
                console.print(
                    "\n[yellow]⚠️  Please save this password securely - you will not see it again![/]"
                )

    run_async(_run())


@click.command()
@click.option("-e", "--email", prompt=True, default=None)
@click.option("-p", "--password", prompt=True, default=None)
def create(email, password):
    """Creates a user using an email."""

    async def _run():
        async with ext.async_session_factory() as session:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                console.print("[yellow]User already exists![/]")
            else:
                user = User(
                    email=email,
                    password=hash_password(password),
                    active=True,
                    confirmed_at=datetime.now(),
                )
                session.add(user)
                await session.commit()

    run_async(_run())


@click.command()
@click.option("-e", "--email", prompt=True, default=None)
@click.option("-r", "--role", prompt=True, default="admin")
def add_role(email, role):
    """Adds a role to the specified user."""

    async def _run():
        from stk.user.models import Role

        async with ext.async_session_factory() as session:
            u = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()

            if u is None:
                console.print("[red]Sorry, this user does not exist![/]")
            else:
                r = (
                    await session.execute(select(Role).where(Role.name == role))
                ).scalar_one_or_none()
                if r is None:
                    console.print("[yellow]Sorry, this role does not exist![/]")
                    answer = click.prompt(
                        "Would you like to create one? Y/N", default="N"
                    )
                    if answer.lower() == "y":
                        r = Role(name=role)
                        try:
                            session.add(r)
                            await session.commit()
                            console.print(
                                "[green]Role created successfully, you may add it now to the user[/]"
                            )
                        except Exception:
                            await session.rollback()
                if r:
                    u.roles.append(r)
                    await session.commit()

    run_async(_run())


@click.command("cleanup-sessions")
def cleanup_sessions():
    """Deactivate expired sessions and delete old rows."""
    from stk.tasks import cleanup_expired_sessions

    run_async(cleanup_expired_sessions())
    console.print("[green]Session cleanup complete[/]")


@click.command()
@click.option("-e", "--email", prompt="Email", default=None)
@click.option("-p", "--password", hide_input=True, prompt=True, default=None)
def reset(email, password):
    """Reset a user password using email"""
    try:
        pwd = hash_password(password)

        async def _run():
            async with ext.async_session_factory() as session:
                u = (
                    await session.execute(select(User).where(User.email == email))
                ).scalar_one_or_none()
                if not u:
                    console.print(f'[red]User with email "{email}" not found.[/]')
                    return

                u.password = pwd
                try:
                    await session.commit()
                    console.print(
                        "[green]User password has been reset successfully.[/]"
                    )
                except Exception:
                    await session.rollback()
                    console.print("[red]Error committing to database.[/]")

        run_async(_run())
    except Exception as e:
        console.print(f"[red]Error resetting user password: {e}[/]")


@click.command()
def migrate():
    """Apply all database migrations (legacy alias for upgrade head)."""
    command.upgrade(build_alembic_config(), "head")


@click.command("migration-status")
def migration_status():
    """Show the current Alembic migration revision."""
    command.current(build_alembic_config())


@click.command("new")
@click.argument("name")
def new_module(name):
    """Scaffold a new blueprint module.

    NAME must be a lowercase snake_case identifier (e.g. blog_post).
    Generates blueprint package, template, and wires into app.py + navigation.js.
    """
    from stk.scaffold.generator import generate_module

    try:
        actions = generate_module(name)
    except (ValueError, FileExistsError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(f"\n[green]Scaffolded blueprint:[/] [bold]{name}[/]")
    for action in actions:
        console.print(f"  [blue]+[/] {action}")

    console.print(
        f"""
[yellow]Post-generation checklist:[/]
  1. Customize [bold]stk/{name}/models.py[/] -- add/rename fields to fit your domain.
  2. Run migration autogenerate:
       [bold]uv run quart db revision -m "add {name}"[/]
     Review [bold]alembic/versions/<rev>_add_{name}.py[/] for correctness.
  3. Apply migration:
       [bold]uv run quart db upgrade[/]
  4. Verify:
       [bold]uv run quart verify && uv run quart smoke[/]
"""
    )
