"""Machine-readable reports behind `quart inspect`, `verify`, and `report`."""

import html
import inspect as pyinspect
import subprocess
import sys
from pathlib import Path

from stk.migrations import import_model_modules

VERIFY_COMMANDS = [
    ("ruff", ["ruff", "check", "."]),
    ("checks", [sys.executable, "checks.py"]),
    ("migration-drift", [sys.executable, "-m", "quart", "db", "check"]),
]


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


def _guards(func):
    """Return the quart-security guards wrapping `func`, outermost first.

    ponytail: identifies the guards by the decorator's closure qualname because
    quart-security exposes no marker. `checks.py` asserts the result against real
    requests, so a rename upstream fails the gate instead of silently reporting
    every route as open.
    """
    guards = []
    while func is not None:
        qualname = getattr(getattr(func, "__code__", None), "co_qualname", "")
        for guard in ("auth_required", "roles_required"):
            if qualname.startswith(f"{guard}."):
                guards.append(guard)
        func = getattr(func, "__wrapped__", None)
    return guards


def _route_auth(app, rule):
    """Report whether a route is guarded, and where the guard is declared."""
    if rule.rule.startswith("/_test/"):
        return {"required": False, "source": "test-only", "scheme": "agent-token"}

    blueprint = rule.endpoint.rsplit(".", 1)[0] if "." in rule.endpoint else None
    if _guards(app.view_functions.get(rule.endpoint)):
        return {"required": True, "source": "route", "scheme": "session"}

    for func in app.before_request_funcs.get(blueprint, []):
        if _guards(func):
            return {"required": True, "source": "blueprint", "scheme": "session"}

    return {"required": False, "source": "unguarded", "scheme": "public"}


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
                "auth": _route_auth(app, rule),
                "source": _route_source(view_func),
            }
        )
    return routes


def build_models_report():
    """Return model metadata in a compact, agent-readable shape."""
    from stk.extensions import Base

    import_model_modules()
    models = {}
    for table_name, table in sorted(Base.metadata.tables.items()):
        models[table_name] = {
            "columns": [
                {
                    "name": column.name,
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                }
                for column in table.columns
            ],
            "indexes": sorted(index.name for index in table.indexes if index.name),
        }
    return models


def build_context_report(app):
    """Return the project context contract used by agents and tooling."""
    return {
        "routes": build_routes_report(app),
        "models": build_models_report(),
    }


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
