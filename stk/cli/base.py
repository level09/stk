"""Shared CLI plumbing: console output and the sync/async bridge."""

import asyncio

from rich.console import Console

import stk.extensions as ext

console = Console()


def run_async(coro):
    """Run an async function in sync context (for CLI commands)."""

    async def _wrapper():
        try:
            return await coro
        finally:
            if ext.engine:
                await ext.engine.dispose()

    return asyncio.run(_wrapper())
