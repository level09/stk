"""Async REPL for stk: live app, live DB session, top-level await."""

from __future__ import annotations

import ast
import asyncio
import atexit
import code
import inspect
import sys
import types
from datetime import datetime, timedelta
from pathlib import Path

from quart import g
from rich.console import Console
from sqlalchemy import delete, func, select, text, update

import stk.extensions as ext
from stk.migrations import import_model_modules

console = Console()

HISTORY_FILE = (
    Path(__file__).resolve().parent.parent / "instance" / ".stk_shell_history"
)
BANNER_HELPERS = [
    ("find(Model, **kw)", "list rows matching equality filters"),
    ("first(Model, **kw)", "first row matching equality filters"),
    ("count(Model, **kw)", "row count"),
    ("sql('select 1')", "run raw SQL, return rows"),
    ("routes('user')", "print routes, optionally filtered"),
    ("db", "live AsyncSession (also g.db_session)"),
]


def discover_models() -> dict[str, type]:
    """Return every mapped model class keyed by class name."""
    import_model_modules()
    return {
        mapper.class_.__name__: mapper.class_ for mapper in ext.Base.registry.mappers
    }


def build_namespace(app, db) -> dict:
    """Build the shell namespace: app, session, models, query helpers."""
    from stk.cli.reports import build_routes_report

    async def find(model, **filters):
        stmt = select(model).filter_by(**filters)
        return (await db.execute(stmt)).scalars().all()

    async def first(model, **filters):
        stmt = select(model).filter_by(**filters).limit(1)
        return (await db.execute(stmt)).scalars().first()

    async def count(model, **filters):
        stmt = select(func.count()).select_from(model).filter_by(**filters)
        return (await db.execute(stmt)).scalar_one()

    async def sql(statement, **params):
        result = await db.execute(
            text(statement) if isinstance(statement, str) else statement, params
        )
        return result.all() if result.returns_rows else result.rowcount

    def routes(pattern=None):
        for route in build_routes_report(app):
            if (
                pattern
                and pattern not in route["rule"]
                and pattern not in route["endpoint"]
            ):
                continue
            methods = ",".join(route["methods"])
            lock = "[yellow]auth[/]" if route["auth"]["required"] else "[dim]open[/]"
            console.print(
                f"[dim]{methods:14}[/]{route['rule']:44} {lock:16} [cyan]{route['endpoint']}[/]",
                soft_wrap=True,
            )

    namespace = {
        "app": app,
        "db": db,
        "ext": ext,
        "select": select,
        "func": func,
        "text": text,
        "delete": delete,
        "update": update,
        "datetime": datetime,
        "timedelta": timedelta,
        "find": find,
        "first": first,
        "count": count,
        "sql": sql,
        "routes": routes,
    }
    namespace.update(discover_models())
    return namespace


def print_banner(models) -> None:
    console.print(f"\n[bold]stk shell[/] [dim]python {sys.version.split()[0]}[/]")
    console.print(f"[dim]db:[/] {_masked_database_url()}")
    console.print(f"[dim]models:[/] {', '.join(models)}")
    for name, description in BANNER_HELPERS:
        console.print(f"  [green]{name:22}[/] [dim]{description}[/]")
    console.print("[dim]top-level await works. ctrl-d to exit.[/]\n")


def _masked_database_url() -> str:
    from sqlalchemy.engine import make_url

    from stk.settings import Config

    return make_url(Config.SQLALCHEMY_DATABASE_URI).render_as_string(hide_password=True)


def _setup_readline(namespace) -> None:
    """Tab completion and persistent history, best effort."""
    try:
        import readline
        import rlcompleter
    except ImportError:  # pragma: no cover - windows / no readline build
        return

    readline.set_completer(rlcompleter.Completer(namespace).complete)
    readline.parse_and_bind(
        "bind ^I rl_complete"
        if "libedit" in getattr(readline, "__doc__", "")
        else "tab: complete"
    )
    readline.set_history_length(2000)
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        if HISTORY_FILE.exists():
            readline.read_history_file(str(HISTORY_FILE))
    except OSError:  # unreadable history is not worth failing the shell over
        return
    atexit.register(readline.write_history_file, str(HISTORY_FILE))


def build_awaiter(app, db, loop):
    """Await a coroutine inside a fresh app context, like a request would."""

    def await_(coro):
        async def _wrapped():
            async with app.app_context():
                g.db_session = db
                return await coro

        return loop.run_until_complete(_wrapped())

    return await_


class AsyncConsole(code.InteractiveConsole):
    """InteractiveConsole that awaits top-level coroutines on a shared loop."""

    def __init__(self, namespace, await_):
        super().__init__(namespace)
        self.await_ = await_
        self.compile.compiler.flags |= ast.PyCF_ALLOW_TOP_LEVEL_AWAIT

    def runcode(self, code_obj):
        try:
            result = types.FunctionType(code_obj, self.locals)()
            if inspect.iscoroutine(result):
                self.await_(result)
        except SystemExit:
            raise
        except BaseException:
            self.showtraceback()


def run_shell(app, source: str | None = None) -> None:
    """Start the REPL, or execute `source` and print its result."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    db = ext.async_session_factory()
    await_ = build_awaiter(app, db, loop)
    namespace = build_namespace(app, db)

    try:
        if source is not None:
            _run_source(await_, namespace, source)
            return
        _setup_readline(namespace)
        print_banner(sorted(discover_models()))
        AsyncConsole(namespace, await_).interact(banner="", exitmsg="")
    finally:
        loop.run_until_complete(db.close())
        if ext.engine:
            loop.run_until_complete(ext.engine.dispose())
        loop.close()


def _run_source(await_, namespace, source: str) -> None:
    """Execute one-shot source with top-level await; print the last expression."""
    block = ast.parse(source, mode="exec")
    last = (
        block.body.pop()
        if block.body and isinstance(block.body[-1], ast.Expr)
        else None
    )

    def run(node, mode):
        code_obj = compile(
            node, "<stk shell>", mode, flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT
        )
        result = types.FunctionType(code_obj, namespace)()
        return await_(result) if inspect.iscoroutine(result) else result

    if block.body:
        run(block, "exec")
    if last is not None:
        result = run(ast.Expression(last.value), "eval")
        if result is not None:
            print(result)
