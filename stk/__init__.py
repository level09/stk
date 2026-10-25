"""
stk Framework
A modern Python web framework optimized for AI-assisted development.
"""

__version__ = "17.0.0"


def __getattr__(name):
    # Lazy, so `import stk` loads no app code until a name is used.
    if name == "Stk":
        from stk.app import Stk

        return Stk
    if name in ("Config", "TestingConfig"):
        from stk import settings

        return getattr(settings, name)
    raise AttributeError(f"module 'stk' has no attribute {name!r}")
