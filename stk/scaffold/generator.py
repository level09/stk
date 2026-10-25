"""Filesystem operations for the scaffolder.

generate_app() writes a new app package (`stk init`); generate_module() writes
an extension into an existing app and adds it to the app's extension list
(`stk new`). Neither touches stk's own files.
"""

import os
import re
import secrets
import shutil
import sys
from pathlib import Path

import stk
from stk.scaffold.templates import (
    render_init,
    render_models,
    render_template_html,
    render_views,
)

APP_TEMPLATE = Path(__file__).parent / "app"
# Template files stored without a leading dot, so packaging never drops them.
DOTFILES = {
    "gitignore": ".gitignore",
    "dockerignore": ".dockerignore",
    "env-sample": ".env-sample",
}

# Names that conflict with existing blueprints, SQLAlchemy reserved words, or
# Python builtins that would make imports ambiguous.
RESERVED = frozenset(
    {
        "user",
        "users",
        "role",
        "public",
        "portal",
        "websocket",
        "ws",
        "activity",
        "session",
        "security",
        "oauth",
        "webauthn",
        "admin",
        "static",
        "templates",
        "migrations",
        "api",
        "app",
        "stk",
        "test",
        "tests",
        "settings",
        # Python builtins
        "type",
        "list",
        "dict",
        "set",
        "tuple",
        "int",
        "str",
        "float",
        "bool",
        "bytes",
        "object",
        "id",
    }
)

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_name(name: str) -> None:
    """Raise ValueError with a clear message if name is invalid."""
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Name '{name}' is not valid. Use lowercase snake_case identifiers "
            "(letters, digits, underscores; must start with a letter)."
        )
    if name in RESERVED:
        raise ValueError(f"Name '{name}' is reserved. Choose a different name.")


def _local_source(target: Path, source: str) -> str:
    """The `[tool.uv.sources]` entry that installs stk from a local path."""
    path = Path(source).resolve()
    if not path.exists():
        raise ValueError(f"--source {source} does not exist")
    relative = Path(os.path.relpath(path, target)).as_posix()
    editable = ", editable = true" if path.is_dir() else ""
    return f'stk = {{ path = "{relative}"{editable} }}'


def _env(sample: str) -> str:
    """A development .env from the sample, with fresh secrets."""
    for key in ("SECRET_KEY", "SECURITY_PASSWORD_SALT"):
        sample = sample.replace(
            f"\n{key}=\n", f'\n{key}="{secrets.token_urlsafe(32)}"\n'
        )
    return sample


def generate_app(name: str, target: Path, source: str | None = None) -> list[str]:
    """Write a new app package at `target` from the app template."""
    validate_name(name)
    if target.exists():
        raise FileExistsError(f"{target} already exists. Choose another directory.")

    major = int(stk.__version__.split(".")[0])
    tokens = {
        "__app__": name,
        "__App__": name.replace("_", " ").title(),
        "__stk_version__": stk.__version__,
        "__stk_next__": str(major + 1),
    }
    actions = []
    for template in sorted(APP_TEMPLATE.rglob("*")):
        relative = template.relative_to(APP_TEMPLATE)
        # Tool caches (__pycache__, .ruff_cache) are not part of the template.
        if template.is_dir() or any(
            part.startswith((".", "__pycache__")) for part in relative.parts
        ):
            continue
        parts = [
            DOTFILES.get(part, part).replace("__app__", name) for part in relative.parts
        ]
        path = target.joinpath(*parts)
        text = template.read_text()
        for token, value in tokens.items():
            text = text.replace(token, value)
        if source is not None and parts == ["pyproject.toml"]:
            text = re.sub(
                r"^stk = \{ git = .*$", _local_source(target, source), text, flags=re.M
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        shutil.copymode(template, path)
        actions.append(f"created {path.relative_to(target.parent)}")

    (target / ".env").write_text(_env((target / ".env-sample").read_text()))
    actions.append(
        f"created {(target / '.env').relative_to(target.parent)} (fresh secrets)"
    )
    return actions


def _add_extension(source: str, package: str, name: str) -> str:
    """Import `name` in the app module and append it to `extensions = [...]`."""
    listing = re.search(r"^extensions = \[([^\]]*)\]", source, re.M)
    if listing is None:
        raise RuntimeError(
            f"no `extensions = [...]` line in the app module. Add {package}.{name} "
            "to the list you pass to Stk(extensions=...) by hand."
        )
    items = [item.strip() for item in listing.group(1).split(",") if item.strip()]
    if name not in items:
        items.append(name)
    source = source.replace(listing.group(0), f"extensions = [{', '.join(items)}]")

    imports = re.search(rf"^from {package} import ([\w, ]+)$", source, re.M)
    if imports:
        names = sorted({*imports.group(1).split(", "), name})
        return source.replace(
            imports.group(0), f"from {package} import {', '.join(names)}"
        )
    anchor = re.search(rf"^from {package}\.", source, re.M)
    if anchor is None:
        raise RuntimeError(f"add `from {package} import {name}` to the app module")
    return (
        source[: anchor.start()]
        + f"from {package} import {name}\n"
        + source[anchor.start() :]
    )


def generate_module(name: str, app) -> list[str]:
    """Write an extension package into the app and add it to the app's list."""
    validate_name(name)
    root = Path(app.root_path)
    package = app.import_name.split(".")[0]
    app_module = Path(sys.modules[app.import_name].__file__)
    module = root / name
    if module.exists():
        raise FileExistsError(f"{module} already exists. Remove it first.")

    files = {
        module / "__init__.py": render_init(name, package),
        module / "models.py": render_models(name),
        module / "views.py": render_views(name, package),
        module / "templates" / name / "index.html": render_template_html(name),
    }
    project = root.parent
    actions = []
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        actions.append(f"created {path.relative_to(project)}")

    app_module.write_text(_add_extension(app_module.read_text(), package, name))
    actions.append(
        f"added {name} to the extensions in {app_module.relative_to(project)}"
    )
    return actions
