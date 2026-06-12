"""Filesystem operations for the scaffolder.

generate_module() is the single entry point -- it writes files and patches
app.py + navigation.js. All path logic is centralised here.
"""

import re
from pathlib import Path

from stk.scaffold.templates import (
    render_app_import,
    render_app_register,
    render_init,
    render_models,
    render_nav_entry,
    render_template_html,
    render_views,
)

# Names that conflict with existing blueprints, SQLAlchemy reserved words, or
# Python builtins that would make imports ambiguous.
RESERVED = frozenset(
    {
        "user",
        "role",
        "public",
        "portal",
        "websocket",
        "activity",
        "session",
        "oauth",
        "webauthn",
        "admin",
        "static",
        "api",
        "test",
        "tests",
        "scaffold",
        "extensions",
        "commands",
        "migrations",
        "settings",
        "tasks",
        "utils",
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

# Markers used for idempotent text insertion into app.py
_IMPORT_ANCHOR = "from stk.websocket import ws_bp\n"
_REGISTER_ANCHOR = "    app.register_blueprint(ws_bp)\n"

# Marker used for navigation.js insertion
_NAV_ANCHOR = "  {\n    title: 'Activity Logs',"


def validate_name(name: str) -> None:
    """Raise ValueError with a clear message if name is invalid."""
    if not _NAME_RE.match(name):
        raise ValueError(
            f"Name '{name}' is not valid. Use lowercase snake_case identifiers "
            "(letters, digits, underscores; must start with a letter)."
        )
    if name in RESERVED:
        raise ValueError(f"Name '{name}' is reserved. Choose a different name.")


def _project_root() -> Path:
    """Return the project root (parent of the stk package)."""
    return Path(__file__).resolve().parent.parent.parent


def scaffold_paths(name: str, root: Path | None = None) -> dict[str, Path]:
    """Return a dict of {key: absolute Path} for all generated files."""
    r = root or _project_root()
    return {
        "pkg_init": r / "stk" / name / "__init__.py",
        "pkg_models": r / "stk" / name / "models.py",
        "pkg_views": r / "stk" / name / "views.py",
        "template": r / "stk" / "templates" / "cms" / f"{name}.html",
        "app_py": r / "stk" / "app.py",
        "nav_js": r / "stk" / "static" / "js" / "navigation.js",
    }


def generate_module(name: str, root: Path | None = None) -> list[str]:
    """Write all scaffold files and patch app.py + navigation.js.

    Returns a list of human-readable action strings for the checklist.

    Raises ValueError on invalid name or FileExistsError if blueprint dir exists.
    """
    validate_name(name)

    r = root or _project_root()
    paths = scaffold_paths(name, r)

    pkg_dir = paths["pkg_init"].parent
    if pkg_dir.exists():
        raise FileExistsError(
            f"Blueprint directory {pkg_dir} already exists. Remove it first."
        )

    actions: list[str] = []

    # 1. Blueprint package
    pkg_dir.mkdir(parents=True)
    paths["pkg_init"].write_text(render_init(name))
    actions.append(f"created {paths['pkg_init'].relative_to(r)}")

    paths["pkg_models"].write_text(render_models(name))
    actions.append(f"created {paths['pkg_models'].relative_to(r)}")

    paths["pkg_views"].write_text(render_views(name))
    actions.append(f"created {paths['pkg_views'].relative_to(r)}")

    # 2. Template
    paths["template"].parent.mkdir(parents=True, exist_ok=True)
    paths["template"].write_text(render_template_html(name))
    actions.append(f"created {paths['template'].relative_to(r)}")

    # 3. Patch app.py (import + register)
    app_text = paths["app_py"].read_text()
    import_line = render_app_import(name)
    register_line = render_app_register(name)

    if import_line not in app_text:
        if _IMPORT_ANCHOR not in app_text:
            raise RuntimeError(
                f"Could not find import anchor '{_IMPORT_ANCHOR.strip()}' in app.py. "
                "Patch app.py manually."
            )
        app_text = app_text.replace(_IMPORT_ANCHOR, _IMPORT_ANCHOR + import_line)
        actions.append(f"patched stk/app.py: added import for bp_{name}")
    else:
        actions.append("stk/app.py import already present (idempotent)")

    if register_line not in app_text:
        if _REGISTER_ANCHOR not in app_text:
            raise RuntimeError(
                "Could not find register anchor in app.py. Patch register_blueprints() manually."
            )
        app_text = app_text.replace(_REGISTER_ANCHOR, _REGISTER_ANCHOR + register_line)
        actions.append(f"patched stk/app.py: registered bp_{name}")
    else:
        actions.append("stk/app.py register already present (idempotent)")

    paths["app_py"].write_text(app_text)

    # 4. Patch navigation.js
    nav_text = paths["nav_js"].read_text()
    nav_entry = render_nav_entry(name)

    if f"to: '/{name}s'" not in nav_text:
        if _NAV_ANCHOR not in nav_text:
            raise RuntimeError(
                f"Could not find navigation anchor in navigation.js. Add the nav entry manually:\n{nav_entry}"
            )
        nav_text = nav_text.replace(_NAV_ANCHOR, nav_entry + _NAV_ANCHOR)
        paths["nav_js"].write_text(nav_text)
        actions.append(
            f"patched stk/static/js/navigation.js: added nav entry for {name}"
        )
    else:
        actions.append("navigation.js entry already present (idempotent)")

    return actions
