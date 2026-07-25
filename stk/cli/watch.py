"""File watching for `stk verify --watch`, with no watcher dependency.

A polling scan over the project's own source files. The tree is small (a few
hundred files), so a stat() sweep twice a second costs less than importing a
watcher library would.
"""

from pathlib import Path

IGNORED_DIRS = {
    ".git",
    ".venv",
    ".ruff_cache",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    "instance",
    ".stk",
    "alembic",
}
# Checks worth re-running when a file of this kind changes. Also defines what
# counts as a source file, so the two can never disagree.
CHECKS_BY_SUFFIX = {
    ".py": ("ruff", "checks", "migration-drift"),
    ".html": ("checks",),
    ".jinja2": ("checks",),
    ".js": ("checks",),
    ".css": ("checks",),
}
# Vendored assets are refreshed by vendor.sh, not edited, and they are large.
IGNORED_PARTS = {"static/js/vue.min.js", "static/js/vuetify.min.js"}


def scan(root: Path) -> dict[Path, float]:
    """Return {path: mtime} for every source file worth reacting to."""
    seen = {}
    for path in root.rglob("*"):
        if path.suffix not in CHECKS_BY_SUFFIX:
            continue
        if IGNORED_DIRS & set(path.parts):
            continue
        if any(part in path.as_posix() for part in IGNORED_PARTS):
            continue
        try:
            seen[path] = path.stat().st_mtime
        except OSError:  # deleted between rglob and stat
            continue
    return seen


def changed(previous: dict[Path, float], current: dict[Path, float]) -> list[Path]:
    """Return the paths that were added, removed, or touched."""
    touched = [
        path
        for path, mtime in current.items()
        if previous.get(path) != mtime  # new file or new mtime
    ]
    touched += [path for path in previous if path not in current]
    return sorted(set(touched))


def checks_for(paths) -> list[str]:
    """Return the check names worth re-running for this batch of changes."""
    names = []
    for path in paths:
        for name in CHECKS_BY_SUFFIX.get(path.suffix, ()):
            if name not in names:
                names.append(name)
    return names
