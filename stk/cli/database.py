"""Database and migration commands."""

import click
from alembic import command

from stk.cli.base import cli_app, console
from stk.migrations import (
    CORE_LABEL,
    app_label,
    app_versions,
    build_alembic_config,
    get_target_metadata,
    throwaway_database_url,
)


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


def build_migration_drift_report(app=None, database_url=None):
    """Return differences between the migrations at their heads and the models.

    Migrations run against a throwaway database of the app's dialect, so the
    answer does not depend on the state of any developer machine. With no app,
    stk's own lineage is checked against its own models.
    """
    from alembic.autogenerate import compare_metadata
    from alembic.runtime.migration import MigrationContext
    from sqlalchemy import create_engine

    from stk.migrations import include_object

    if database_url is None:
        database_url = app.config["SQLALCHEMY_DATABASE_URI"]
    with throwaway_database_url(database_url, sync=True) as url:
        config = build_alembic_config(app, url, quiet=True)
        command.upgrade(config, "heads")

        engine = create_engine(url)
        try:
            with engine.connect() as connection:
                context = MigrationContext.configure(
                    connection,
                    opts={
                        "compare_type": True,
                        "compare_server_default": True,
                        "include_object": include_object,
                    },
                )
                diffs = compare_metadata(context, get_target_metadata())
        finally:
            engine.dispose()

    return [_describe_diff(diff) for diff in _flatten(diffs)]


def generate_revision(app, message, *, autogenerate=True, head=None, quiet=False):
    """Write a revision in the app's lineage, or in `head`'s when given.

    The app's first revision starts its branch. Every app revision depends on
    stk's head at the time it is written, so core tables (`user`) exist first.
    """
    from alembic.script import ScriptDirectory

    config = build_alembic_config(app, quiet=quiet)
    if head is not None:
        return run_alembic(
            command.revision,
            config,
            message=message,
            autogenerate=autogenerate,
            head=head,
        )
    script = ScriptDirectory.from_config(config)
    label = app_label(app)
    started = any(label in rev.branch_labels for rev in script.walk_revisions())
    core_head = script.get_revision(f"{CORE_LABEL}@head").revision
    options = (
        {"head": f"{label}@head"}
        if started
        else {
            "head": "base",
            "branch_label": label,
            "version_path": str(app_versions(app)),
        }
    )
    app_versions(app).mkdir(exist_ok=True)
    return run_alembic(
        command.revision,
        config,
        message=message,
        autogenerate=autogenerate,
        depends_on=core_head,
        **options,
    )


@click.command()
def create_db():
    """Apply all database migrations (same as `stk db upgrade`)."""
    run_alembic(command.upgrade, build_alembic_config(cli_app()), "heads")
    console.print("[green]Database migrations applied successfully[/]")


@click.group()
def db():
    """Alembic-backed database migration commands."""


@db.command("upgrade")
@click.argument("revision", default="heads")
def db_upgrade(revision):
    """Upgrade the database: stk's migrations and the app's, to their heads."""
    run_alembic(command.upgrade, build_alembic_config(cli_app()), revision)


# Relative targets like "-1" look like options to click; accept them as the argument.
@db.command("downgrade", context_settings={"ignore_unknown_options": True})
@click.argument("revision")
def db_downgrade(revision):
    """Downgrade the database to a target revision."""
    run_alembic(command.downgrade, build_alembic_config(cli_app()), revision)


@db.command("revision")
@click.option("-m", "--message", required=True, help="Revision message")
@click.option(
    "--autogenerate/--empty",
    default=True,
    help="Autogenerate from model metadata or create an empty revision",
)
@click.option(
    "--head",
    default=None,
    help="Extend this head instead of the app's lineage (stk@head for core).",
)
def db_revision(message, autogenerate, head):
    """Create a migration revision in the app's own lineage."""
    generate_revision(cli_app(), message, autogenerate=autogenerate, head=head)


@db.command("check")
def db_check():
    """Fail if models have drifted away from the migrations."""
    try:
        drift = build_migration_drift_report(cli_app())
    except RuntimeError as exc:
        raise click.ClickException(str(exc)) from exc
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
    run_alembic(command.current, build_alembic_config(cli_app()))


@db.command("history")
def db_history():
    """Show migration history."""
    run_alembic(command.history, build_alembic_config(cli_app()))


@db.command("stamp")
@click.argument("revision", default="heads")
def db_stamp(revision):
    """Stamp a database with a revision without running migrations."""
    run_alembic(command.stamp, build_alembic_config(cli_app()), revision)
