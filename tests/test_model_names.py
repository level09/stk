"""Apps share stk's declarative Base, so class names share one string registry."""

import subprocess
import sys
import unittest

# Names apps are meant to reference, by string included.
IDENTITY = {"User", "Role"}
# Generic names that predate the Stk prefix rule. Never add to this list.
LEGACY = {
    "Activity",
    "File",
    "Job",
    "McpToken",
    "Notification",
    "OAuth",
    "RateLimitWindow",
    "Session",
    "WebAuthn",
}


class ModelNameTests(unittest.TestCase):
    def test_new_core_models_carry_the_stk_prefix(self):
        """A generic core name breaks every app with a model of that name."""
        import stk.files.models  # noqa: F401
        import stk.mcp.models  # noqa: F401
        import stk.notification.models  # noqa: F401
        import stk.tasks.models  # noqa: F401
        import stk.user.models  # noqa: F401
        import stk.websocket  # noqa: F401
        from stk.extensions import Base

        core = {
            mapper.class_.__name__
            for mapper in Base.registry.mappers
            if mapper.class_.__module__.startswith("stk.")
        }
        unprefixed = sorted(
            name for name in core - IDENTITY - LEGACY if not name.startswith("Stk")
        )
        self.assertEqual(unprefixed, [], "name new core models Stk<Name>")

    def test_app_models_may_reuse_core_names(self):
        """Core refers to its own models by class, so app names never break it."""
        script = (
            "from sqlalchemy import Column, ForeignKey, Integer\n"
            "from sqlalchemy.orm import configure_mappers, relationship\n"
            "import stk.user.models, stk.websocket\n"
            "from stk.extensions import Base\n"
            "def model(name, table):\n"
            "    return type(name, (Base,), {'__tablename__': table,\n"
            "        'id': Column(Integer, primary_key=True)})\n"
            "for name in ('User', 'Role', 'WebAuthn'):\n"
            "    model(name, f'app_{name.lower()}')\n"
            "class Message(Base):\n"
            "    __tablename__ = 'app_message'\n"
            "    id = Column(Integer, primary_key=True)\n"
            "    parent_id = Column(Integer, ForeignKey('app_message.id'))\n"
            "    replies = relationship('Message', lazy='selectin')\n"
            "configure_mappers()\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", script], capture_output=True, text=True
        )
        self.assertEqual(result.returncode, 0, result.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
