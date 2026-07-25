"""Database and migration commands."""

import os
import tempfile
from pathlib import Path

import click

from alembic import command
from stk.cli.base import console
from stk.migrations import build_alembic_config, get_target_metadata


def run_alembic(action, *args, **kwargs):
    """Run an alembic command, reporting its complaint instead of a traceback."""
    from alembic.util.exc import CommandError

    try:
        return action(*args, **kwargs)
    except CommandError as exc:
        raise click.ClickException(f"{exc}\nrun: uv run stk doctor") from exc


def _flatten(diffs):
    for diff in diffs:
        if isinstance(diff, list):
            yield from diff
        else:
            yield diff


def _describe_diff(diff):
    """Render an autogenerate diff tuple as one readable line."""
    parts = []
    for element in diff[1:]:
        if element is None or isinstance(element, dict):  # schema, autogenerate opts
            continue
        parts.append(str(getattr(element, "name", element)))
    return f"{diff[0]}: {' '.join(parts)}".strip()


def build_migration_drift_report():
    """Return differences between the migrations at head and model metadata.

    Migrations run against a throwaway database, so the answer does not depend
    on the state of any developer machine.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    with tempfile.TemporaryDirectory(prefix="stk-drift-") as temp_dir:
        # ponytail: SQLite stands in for any dialect; revisit if models grow
        # Postgres-only types that autogenerate renders differently.
        config = build_alembic_config()
        # env.py skips fileConfig without an ini path: migrating the throwaway
        # database is an implementation detail, not output.
        config.config_file_name = None
        config.set_main_option("sqlalchemy.url", f"sqlite:///{Path(temp_dir)}/drift.db")
        command.upgrade(config, "head")

        engine = create_engine(config.get_main_option("sqlalchemy.url"))
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection,
                    opts={"compare_type": True, "compare_server_default": True},
                )
                diffs = compare_metadata(context, get_target_metadata())
        finally:
            engine.dispose()

    return [_describe_diff(diff) for diff in _flatten(diffs)]


@click.command()
def create_db():
    """Apply all database migrations."""
    from stk.settings import Config

    instance_dir = os.path.join(Config.PROJECT_ROOT, "instance")
    os.makedirs(instance_dir, exist_ok=True)
    run_alembic(command.upgrade, build_alembic_config(), "head")
    console.print("[green]Database migrations applied successfully[/]")


@click.group()
def db():
    """Alembic-backed database migration commands."""


@db.command("upgrade")
@click.argument("revision", default="head")
def db_upgrade(revision):
    """Upgrade the database to a target revision."""
    run_alembic(command.upgrade, build_alembic_config(), revision)


@db.command("downgrade")
@click.argument("revision")
def db_downgrade(revision):
    """Downgrade the database to a target revision."""
    run_alembic(command.downgrade, build_alembic_config(), revision)


@db.command("revision")
@click.option("-m", "--message", required=True, help="Revision message")
@click.option(
    "--autogenerate/--empty",
    default=True,
    help="Autogenerate from model metadata or create an empty revision",
)
def db_revision(message, autogenerate):
    """Create a new migration revision."""
    run_alembic(
        command.revision,
        build_alembic_config(),
        message=message,
        autogenerate=autogenerate,
    )


@db.command("check")
def db_check():
    """Fail if models have drifted away from the migrations."""
    drift = build_migration_drift_report()
    if not drift:
        console.print("[green]No migration drift: models match migrations[/]")
        return

    console.print("[red]Migration drift detected:[/]")
    for line in drift:
        console.print(f"  [yellow]{line}[/]")
    raise click.ClickException(
        'run: uv run stk db revision -m "describe change" && uv run stk db upgrade'
    )


@db.command("current")
def db_current():
    """Show the current database revision."""
    run_alembic(command.current, build_alembic_config())


@db.command("history")
def db_history():
    """Show migration history."""
    run_alembic(command.history, build_alembic_config())


@db.command("stamp")
@click.argument("revision", default="head")
def db_stamp(revision):
    """Stamp a database with a revision without running migrations."""
    run_alembic(command.stamp, build_alembic_config(), revision)


@click.command()
def migrate():
    """Apply all database migrations (legacy alias for upgrade head)."""
    run_alembic(command.upgrade, build_alembic_config(), "head")


@click.command("migration-status")
def migration_status():
    """Show the current Alembic migration revision."""
    run_alembic(command.current, build_alembic_config())
