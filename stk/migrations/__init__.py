"""Alembic integration: stk's lineage ships here, each app keeps its own.

Both lineages share one version table. stk's revisions carry the `stk` branch
label; an app's carry its package name and live in `<package>/migrations/`.
"""

from __future__ import annotations

import importlib
import os
import pkgutil
import tempfile
import uuid
from contextlib import contextmanager
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import make_url

import stk
from stk.extensions import Base

SCRIPT_DIR = Path(__file__).resolve().parent
CORE_VERSIONS = SCRIPT_DIR / "versions"
CORE_LABEL = "stk"

SYNC_DRIVER_MAP = {
    "postgresql+asyncpg": "postgresql+psycopg2",
    "sqlite+aiosqlite": "sqlite",
}

# Tables an extension owns (PostGIS keeps its reference systems here); no model
# describes them, so autogenerate and the drift check must not offer to drop them.
EXTENSION_TABLES = {"spatial_ref_sys"}


def import_model_modules() -> None:
    """Import every `stk.<feature>.models`; apps import theirs when built."""
    for module in pkgutil.iter_modules(stk.__path__, prefix="stk."):
        model_module = f"{module.name}.models"
        try:
            importlib.import_module(model_module)
        except ModuleNotFoundError as exc:
            if exc.name != model_module:
                raise


def get_target_metadata():
    """Return metadata after loading all model modules."""
    import_model_modules()
    return Base.metadata


def include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and name in EXTENSION_TABLES)


def sync_url(database_url: str) -> str:
    """Convert an async driver URL to the sync driver Alembic uses."""
    url = make_url(database_url)
    drivername = SYNC_DRIVER_MAP.get(url.drivername)
    if drivername is not None:
        url = url.set(drivername=drivername)
    # str(URL) masks the password as *** on SQLAlchemy >= 2.0.50
    return url.render_as_string(hide_password=False)


def app_label(app) -> str:
    """The branch label of an app's lineage: its top-level package name."""
    return app.import_name.split(".")[0]


def app_versions(app) -> Path:
    return Path(app.root_path) / "migrations"


def build_alembic_config(app=None, url=None, *, quiet=False) -> AlembicConfig:
    """Build an Alembic config for stk's lineage plus the app's, if given."""
    config = AlembicConfig()
    config.set_main_option("script_location", str(SCRIPT_DIR))
    config.set_main_option("path_separator", "os")
    locations = [CORE_VERSIONS] + ([app_versions(app)] if app is not None else [])
    config.set_main_option("version_locations", os.pathsep.join(map(str, locations)))
    if url is None:
        url = sync_url(app.config["SQLALCHEMY_DATABASE_URI"])
    # The ini parser behind main options treats % as interpolation.
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["quiet"] = quiet
    return config


def portable_tables() -> list:
    """Every model table except those marked `info={"postgis": True}`, for SQLite."""
    return [t for t in get_target_metadata().sorted_tables if not t.info.get("postgis")]


def _render(url, *, sync: bool) -> str:
    rendered = url.render_as_string(hide_password=False)
    return sync_url(rendered) if sync else rendered


@contextmanager
def throwaway_database_url(database_url: str, *, sync: bool = False):
    """Yield the URL of an empty database of the same dialect, then drop it.

    Postgres apps need Postgres here: their models and migrations use types
    SQLite cannot render. Postgres needs a role with CREATEDB.
    """
    from sqlalchemy import create_engine, text

    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        with tempfile.TemporaryDirectory(prefix="stk-db-") as temp_dir:
            yield _render(url.set(database=f"{temp_dir}/throwaway.db"), sync=sync)
        return

    name = f"stk_tmp_{uuid.uuid4().hex[:12]}"
    admin = create_engine(
        _render(url.set(database="postgres"), sync=True), isolation_level="AUTOCOMMIT"
    )
    try:
        with admin.connect() as connection:
            connection.execute(text(f'create database "{name}"'))
        try:
            yield _render(url.set(database=name), sync=sync)
        finally:
            with admin.connect() as connection:
                connection.execute(text(f'drop database "{name}" with (force)'))
    finally:
        admin.dispose()
