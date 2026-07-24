"""Shell REPL checks: top-level await plumbing and model discovery."""

import asyncio
import io
import unittest
from contextlib import redirect_stdout

from sqlalchemy.exc import PendingRollbackError

from stk.shell import _run_source, build_namespace, discover_models


def _await(coro):
    return asyncio.run(coro)


class RunSourceTest(unittest.TestCase):
    def run_source(self, source, namespace=None):
        namespace = namespace if namespace is not None else {}
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            _run_source(_await, namespace, source)
        return buffer.getvalue().strip(), namespace

    def test_prints_trailing_expression(self):
        output, _ = self.run_source("1 + 1")
        self.assertEqual(output, "2")

    def test_awaits_trailing_expression(self):
        async def value():
            return "awaited"

        output, _ = self.run_source("await value()", {"value": value})
        self.assertEqual(output, "awaited")

    def test_statements_bind_into_namespace(self):
        output, namespace = self.run_source("x = 2\ny = x * 3\ny")
        self.assertEqual(output, "6")
        self.assertEqual(namespace["x"], 2)

    def test_statements_may_await(self):
        async def value():
            return 7

        output, _ = self.run_source("x = await value()\nx", {"value": value})
        self.assertEqual(output, "7")

    def test_statement_only_source_prints_nothing(self):
        output, namespace = self.run_source("x = 5")
        self.assertEqual(output, "")
        self.assertEqual(namespace["x"], 5)


class SessionRecoveryTest(unittest.TestCase):
    """A failed write must not leave every later query raising."""

    class PoisonedSession:
        def __init__(self):
            self.poisoned = True
            self.rollbacks = 0

        async def execute(self, statement, params=None):
            if self.poisoned:
                raise PendingRollbackError("previous flush failed")
            return "rows"

        async def rollback(self):
            self.rollbacks += 1
            self.poisoned = False

    def test_execute_rolls_back_and_retries_once(self):
        session = self.PoisonedSession()
        execute = build_namespace(app=None, db=session)["execute"]

        self.assertEqual(asyncio.run(execute("select 1")), "rows")
        self.assertEqual(session.rollbacks, 1)


class DiscoverModelsTest(unittest.TestCase):
    def test_finds_mapped_models(self):
        models = discover_models()
        self.assertIn("User", models)
        self.assertIn("Role", models)


if __name__ == "__main__":
    unittest.main()
