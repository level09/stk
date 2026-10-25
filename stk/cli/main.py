"""The `stk` command: one entry point for the whole framework.

Wraps Quart's own CLI group. Every command in `stk/cli/__init__.py` lives on
this group, so commands that need no app (`stk init`) run anywhere. The app is
found from `[tool.stk] app` in the nearest pyproject.toml, or from STK_APP, and
commands it registers (`app.cli.add_command`) appear here too.
"""

import inspect
from importlib.metadata import version

import click
from quart.cli import QuartGroup

import stk.cli as cli
from stk.cli.base import load_app

SECTIONS = [
    ("Develop", ["init", "run", "shell", "new", "routes"]),
    ("Database", ["db", "create-db"]),
    ("Verify", ["doctor", "verify", "smoke", "inspect", "report"]),
    (
        "Accounts",
        [
            "install",
            "create",
            "add-role",
            "reset",
            "cleanup-sessions",
            "browser-token",
            "protect-mfa",
        ],
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
    return load_app()


def _print_version(ctx, _param, value):
    if not value or ctx.resilient_parsing:
        return
    # Apps rename the distribution, so report the framework package's own version.
    import stk

    click.echo(f"stk {stk.__version__} (quart {version('quart')})")
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

for _name, _command in inspect.getmembers(cli):
    if isinstance(_command, click.Command):
        main.add_command(_command)
