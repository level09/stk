"""Starting an app and serving it locally."""

from pathlib import Path

import click

import stk
from stk.cli.base import app_root, app_spec, cli_app, console


@click.command("init")
@click.argument("name")
@click.option(
    "--source",
    default=None,
    help="Install stk from this checkout or wheel instead of its release tag.",
)
def init(name, source):
    """Start a new app package NAME in ./NAME, depending on this stk version."""
    from stk.scaffold.generator import generate_app

    try:
        actions = generate_app(name, Path.cwd() / name, source)
    except (ValueError, FileExistsError) as exc:
        raise click.ClickException(str(exc)) from exc

    for action in actions:
        console.print(f"  [blue]+[/] {action}")
    console.print(
        f"""
[green]App {name} is ready.[/] Next:
  cd {name}
  uv run stk db upgrade && uv run stk install
  uv run stk run
"""
    )


@click.command("run")
@click.option("--host", default="127.0.0.1", help="The interface to bind to.")
@click.option("-p", "--port", default=5000, help="The port to bind to.")
@click.option(
    "--reload/--no-reload",
    default=None,
    help="Restart on code changes (default: on when QUART_DEBUG is set).",
)
def run(host, port, reload):
    """Run a local development server (uvicorn, as in production)."""
    import uvicorn
    from quart.helpers import get_debug_flag

    app = cli_app()
    # Hypercorn, Quart's own runner, waits forever on open tabs at Ctrl+C. The
    # timeout ends long-lived streams (/ws, SSE); browsers reconnect.
    uvicorn.run(
        app_spec(),
        host=host,
        port=port,
        reload=get_debug_flag() if reload is None else reload,
        reload_dirs=[app.root_path, str(Path(stk.__file__).parent)],
        app_dir=str(app_root()),
        timeout_graceful_shutdown=3,
    )
