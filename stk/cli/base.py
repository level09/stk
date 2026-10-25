"""Shared CLI plumbing: finding the app, console output, the sync/async bridge."""

import asyncio
import importlib
import os
import sys
import tomllib
from pathlib import Path

import click
from rich.console import Console

import stk.extensions as ext

console = Console()


def project_root() -> Path:
    """The directory of the nearest pyproject.toml, from the working directory up."""
    cwd = Path.cwd()
    for directory in (cwd, *cwd.parents):
        if (directory / "pyproject.toml").is_file():
            return directory
    raise click.ClickException("no pyproject.toml here or above: cd into an app")


def _tool_stk() -> dict:
    pyproject = project_root() / "pyproject.toml"
    return tomllib.loads(pyproject.read_text()).get("tool", {}).get("stk", {})


def app_spec() -> str:
    """The app as `module:attribute`, from STK_APP or `[tool.stk] app`."""
    if spec := os.environ.get("STK_APP"):
        return spec
    if spec := _tool_stk().get("app"):
        return spec
    raise click.ClickException(
        f'{project_root() / "pyproject.toml"} has no [tool.stk] app = "package.app:app".'
        " Start one with: uv run stk init <name>"
    )


def app_root() -> Path:
    """The directory the app's package is imported from.

    The project, unless `[tool.stk] path` names another: stk's own repository
    runs its bundled example that way.
    """
    path = None if os.environ.get("STK_APP") else _tool_stk().get("path")
    return project_root() / path if path else project_root()


def load_app():
    """Import and return the app named by `app_spec()`."""
    module_name, _, attribute = app_spec().partition(":")
    # The project need not be installed: import it from its own directory.
    sys.path.insert(0, str(app_root()))
    return getattr(importlib.import_module(module_name), attribute or "app")


def cli_app():
    """The app for this CLI invocation, loaded once."""
    from quart.cli import ScriptInfo

    return click.get_current_context().ensure_object(ScriptInfo).load_app()


def run_async(coro):
    """Run an async function in sync context (for CLI commands)."""

    async def _wrapper():
        try:
            return await coro
        finally:
            if ext.engine:
                await ext.engine.dispose()

    return asyncio.run(_wrapper())
