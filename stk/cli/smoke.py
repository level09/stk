"""Real-browser smoke check: boot a throwaway app, drive it with Playwright."""

import asyncio
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import click
import httpx

from stk.agent_login import create_agent_login_token
from stk.cli.base import run_async

SMOKE_EMAIL = "smoke@example.com"
SMOKE_PASSWORD = "SmokePassword123!"
SMOKE_SCREENSHOT = Path(".stk/smoke/dashboard.png")

# Text the same colour as what it sits on renders invisible without raising a
# console error, so the browser has to measure it. 3:1 is the WCAG floor for
# large/bold text; below ~1.5 the element is effectively gone.
MIN_CONTRAST_RATIO = 3.0
_CONTRAST_TEMPLATE = """() => {
  const parse = (value) => {
    const parts = value.match(/[\\d.]+/g);
    if (!parts) return null;
    const nums = parts.map(Number);
    const scale = value.startsWith('color(') ? 255 : 1;
    return {r: nums[0] * scale, g: nums[1] * scale, b: nums[2] * scale,
            a: nums.length > 3 ? nums[3] : 1};
  };
  const luminance = ({r, g, b}) => {
    const channel = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const flatten = (fg, bg) => ({
    r: fg.r * fg.a + bg.r * (1 - fg.a),
    g: fg.g * fg.a + bg.g * (1 - fg.a),
    b: fg.b * fg.a + bg.b * (1 - fg.a),
    a: 1,
  });
  const backdrop = (element) => {
    for (let node = element; node; node = node.parentElement) {
      const background = parse(getComputedStyle(node).backgroundColor);
      if (background && background.a > 0.5) return background;
    }
    return {r: 255, g: 255, b: 255, a: 1};
  };
  const findings = [];
  for (const element of document.querySelectorAll('.v-btn, .v-chip, .v-alert')) {
    if (!element.offsetParent || !element.innerText.trim()) continue;
    const foreground = parse(getComputedStyle(element).color);
    if (!foreground) continue;
    const background = backdrop(element);
    const text = flatten(foreground, background);
    const [a, b] = [luminance(text), luminance(background)];
    const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
    if (ratio < __MIN_RATIO__) {
      findings.push({label: element.innerText.trim().slice(0, 32),
                     ratio: Math.round(ratio * 100) / 100});
    }
  }
  return findings;
}"""
CONTRAST_JS = _CONTRAST_TEMPLATE.replace("__MIN_RATIO__", str(MIN_CONTRAST_RATIO))


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

        for finding in page.get("low_contrast", []):
            problems.append(
                f'invisible text: "{finding["label"]}" contrast {finding["ratio"]}:1'
            )

        page_reports.append(
            {
                "name": page["name"],
                "path": page["path"],
                "status_code": status_code,
                "status": "failed" if problems else "passed",
                "console": page.get("console", []),
                "failed_requests": page.get("failed_requests", []),
                "low_contrast": page.get("low_contrast", []),
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
        [sys.executable, "-m", "stk", "db", "upgrade"],
        [
            sys.executable,
            "-m",
            "stk",
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
            "stk",
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
    low_contrast = await page.evaluate(CONTRAST_JS)
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
        "low_contrast": low_contrast,
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
                await _visit_smoke_page(context, base_url, "home", "/"),
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

    for page in pages:
        if page["name"] == "agent-login":
            page["path"] = "/_test/login?token=<redacted>"
    return build_smoke_report(pages, SMOKE_SCREENSHOT)


def run_smoke():
    """Boot a throwaway app on a free port and drive it with a real browser."""
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
            return asyncio.run(_run_playwright_smoke(base_url, token))
        finally:
            _stop_smoke_server(server)


def print_smoke_report(report):
    click.echo(f"Smoke status: {report['status']}")
    click.echo(f"Dashboard screenshot: {report['dashboard_screenshot']}")
    for page in report["pages"]:
        click.echo(f"{page['status'].upper()} {page['name']} {page['path']}")
        click.echo(f"  HTTP: {page['status_code']}")
        for entry in page["console"]:
            click.echo(f"  console {entry['type']}: {entry['text']}")
        for finding in page.get("low_contrast", []):
            click.echo(f"  invisible text: {finding['label']!r} {finding['ratio']}:1")
        for request in page["failed_requests"]:
            click.echo(
                f"  request failed: {request['url']} {request.get('failure') or ''}"
            )
        for problem in page["problems"]:
            click.echo(f"  problem: {problem}")
