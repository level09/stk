"""Agent-facing commands: inspect, verify, smoke, report, shell, scaffold."""

import json
import time
from pathlib import Path

import click

from stk.cli.base import console
from stk.cli.reports import (
    build_context_report,
    build_project_report_html,
    build_routes_report,
    build_verify_report,
)
from stk.cli.smoke import print_smoke_report, run_smoke, smoke_exit_code


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


@inspect_cmd.command("context")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def inspect_context(as_json):
    """Inspect routes and models as one agent-readable contract."""
    from stk.app import create_app

    report = build_context_report(create_app())
    if as_json:
        click.echo(json.dumps(report, indent=2))
        return

    click.echo(
        f"Context: {len(report['routes'])} routes, {len(report['models'])} models"
    )


@click.command()
@click.option("-c", "--command", "source", default=None, help="Run code and exit.")
def shell(source):
    """Async REPL with the app, a live DB session, and all models loaded."""
    from stk.app import create_app
    from stk.shell import run_shell

    run_shell(create_app(), source)


MARKERS = {"passed": "[green]✓[/]", "failed": "[red]✗[/]", "skipped": "[yellow]-[/]"}


def _print_verify_report(report, detail_lines=5):
    for check in report["checks"]:
        console.print(f"{MARKERS[check['status']]} {check['name']}", highlight=False)
        if check["status"] != "failed":
            continue
        output = check["stdout"].strip() or check["stderr"].strip()
        for line in output.splitlines()[-detail_lines:]:
            console.print(f"    [dim]{line}[/]", highlight=False)
        if check["remedy"]:
            console.print(f"    [cyan]→ {check['remedy']}[/]", highlight=False)


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
@click.option(
    "-w", "--watch", is_flag=True, help="Re-run affected checks on every file save."
)
def verify(as_json, watch):
    """Run STK verification checks."""
    if watch:
        _watch_and_verify()
        return

    report = build_verify_report()
    if as_json:
        click.echo(json.dumps(report, indent=2))
        raise click.exceptions.Exit(0 if report["status"] == "passed" else 1)

    _print_verify_report(report)
    raise click.exceptions.Exit(0 if report["status"] == "passed" else 1)


def _watch_and_verify(interval=0.5):
    """Verify now, then re-verify whatever the next edit could have broken."""
    from stk.cli import watch as watcher
    from stk.cli.reports import VERIFY_COMMANDS, WATCHED_SUFFIXES

    root = Path.cwd()
    console.print("[bold]stk verify --watch[/] [dim]ctrl-c to stop[/]\n")
    _print_verify_report(build_verify_report())
    seen = watcher.scan(root)

    while True:
        time.sleep(interval)
        current = watcher.scan(root)
        touched = watcher.changed(seen, current)
        seen = current
        if not touched:
            continue

        names = watcher.checks_for(touched, WATCHED_SUFFIXES)
        if not names:
            continue
        shown = ", ".join(
            str(path.relative_to(root)) if path.is_relative_to(root) else str(path)
            for path in touched[:3]
        )
        extra = f" +{len(touched) - 3}" if len(touched) > 3 else ""
        console.print(f"\n[dim]changed:[/] {shown}{extra}")
        commands = [item for item in VERIFY_COMMANDS if item[0] in names]
        _print_verify_report(build_verify_report(commands))


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def smoke(as_json):
    """Run a real-browser smoke check against a temporary development app."""
    report = run_smoke()
    if as_json:
        click.echo(json.dumps(report, indent=2))
    else:
        print_smoke_report(report)
    raise click.exceptions.Exit(smoke_exit_code(report))


# Named `doctor_cmd` because `stk.cli.doctor` is the module that backs it, and
# importing a submodule rebinds that attribute on the package.
@click.command("doctor")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON.")
def doctor_cmd(as_json):
    """Report the state of this checkout, and what to run for anything wrong."""
    from stk.cli.doctor import build_doctor_report

    report = build_doctor_report()
    if as_json:
        click.echo(json.dumps(report, indent=2))
        raise click.exceptions.Exit(0 if report["status"] != "fail" else 1)

    marks = {"ok": "[green]✓[/]", "warn": "[yellow]![/]", "fail": "[red]✗[/]"}
    for finding in report["findings"]:
        console.print(
            f"{marks[finding['status']]} [bold]{finding['name']:14}[/] {finding['detail']}",
            highlight=False,
        )
        if finding["remedy"]:
            console.print(f"    [cyan]→ {finding['remedy']}[/]", highlight=False)

    summary = {
        "ok": "[green]Everything is ready.[/]",
        "warn": "[yellow]Usable, with the warnings above.[/]",
        "fail": "[red]Fix the failures above before building.[/]",
    }
    console.print(f"\n{summary[report['status']]}")
    raise click.exceptions.Exit(0 if report["status"] != "fail" else 1)


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


@click.command("new")
@click.argument("name")
@click.option(
    "--migrate/--no-migrate",
    default=True,
    help="Autogenerate and apply the migration for the new model.",
)
@click.option("--port", default=5000, show_default=True, help="Port used in the URL.")
def new_module(name, migrate, port):
    """Scaffold a new blueprint module, ending at a page you can open.

    NAME must be a lowercase snake_case identifier (e.g. blog_post).
    Generates blueprint package, template, and wires into app.py + navigation.js.
    """
    from alembic import command
    from stk.migrations import build_alembic_config
    from stk.scaffold.generator import generate_module

    try:
        actions = generate_module(name)
    except (ValueError, FileExistsError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc

    console.print(f"\n[green]Scaffolded blueprint:[/] [bold]{name}[/]")
    for action in actions:
        console.print(f"  [blue]+[/] {action}")

    if migrate:
        config = build_alembic_config()
        # Skip alembic's own logging config; the scaffold output is the message here.
        config.config_file_name = None
        command.revision(config, message=f"add {name}", autogenerate=True)
        command.upgrade(config, "head")
        console.print(f"  [blue]+[/] migration generated and applied for {name}")

    url = f"http://localhost:{port}/{name}s/"
    console.print(f"\n[green]Open:[/] [bold]{url}[/]  [dim](start it with: stk run)[/]")
    console.print(
        f"""[dim]Then:[/]
  Shape the domain in [bold]stk/{name}/models.py[/]{
            ', and re-run `stk db revision -m "..." && stk db upgrade`'
            if migrate
            else ', then `stk db revision -m "add ' + name + '"` and `stk db upgrade`'
        }
  Keep it honest with [bold]stk verify --watch[/] while you edit
"""
    )
