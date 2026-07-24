"""Agent-facing commands: inspect, verify, smoke, report, shell, scaffold."""

import json
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
        if check["status"] == "failed":
            detail = check["stdout"].strip() or check["stderr"].strip()
            for line in detail.splitlines()[-5:]:
                click.echo(f"    {line}")
    raise click.exceptions.Exit(0 if report["status"] == "passed" else 1)


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
