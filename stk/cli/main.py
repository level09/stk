"""The `stk` command: one entry point for the whole framework.

Wraps Quart's own CLI group, so `stk run`, `stk routes`, and every command
registered in `stk/cli/__init__.py` are available without setting QUART_APP.
"""

from importlib.metadata import version

import click
from quart.cli import QuartGroup

SECTIONS = [
    ("Develop", ["run", "shell", "new", "routes"]),
    ("Database", ["db", "create-db", "migrate", "migration-status"]),
    ("Verify", ["verify", "smoke", "inspect", "report"]),
    (
        "Accounts",
        ["install", "create", "add-role", "reset", "cleanup-sessions", "browser-token"],
    ),
]


class StkGroup(QuartGroup):
    """Quart's CLI group, listing commands by what they are for."""

    def format_commands(self, ctx, formatter):
        commands = {}
        for name in self.list_commands(ctx):
            command = self.get_command(ctx, name)
            if command is not None and not command.hidden:
                commands[name] = command

        for title, names in SECTIONS:
            rows = [
                (name, commands.pop(name).get_short_help_str(limit=60))
                for name in names
                if name in commands
            ]
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)

        if commands:
            with formatter.section("Other"):
                formatter.write_dl(
                    [
                        (name, command.get_short_help_str(limit=60))
                        for name, command in sorted(commands.items())
                    ]
                )


def _create_app(**_kwargs):
    from stk.app import create_app

    return create_app()


def _print_version(ctx, _param, value):
    if not value or ctx.resilient_parsing:
        return
    click.echo(f"stk {version('stk')} (quart {version('quart')})")
    ctx.exit()


main = StkGroup(
    name="stk",
    create_app=_create_app,
    add_version_option=False,
    help="stk: async Quart framework with a Vue frontend and no build step.",
    params=[
        click.Option(
            ["-v", "--version"],
            is_flag=True,
            expose_value=False,
            is_eager=True,
            callback=_print_version,
            help="Show the stk version and exit.",
        )
    ],
    context_settings={"help_option_names": ["-h", "--help"]},
)
