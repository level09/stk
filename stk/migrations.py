"""Alembic integration helpers for stk."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from alembic.config import Config as AlembicConfig
from sqlalchemy.engine import make_url

import stk
from stk.extensions import Base
from stk.settings import Config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIR = PROJECT_ROOT / "alembic"

SYNC_DRIVER_MAP = {
    "postgresql+asyncpg": "postgresql+psycopg2",
    "sqlite+aiosqlite": "sqlite",
}


def import_model_modules() -> None:
    """Import all `stk.<feature>.models` modules so metadata is complete."""
    for module in pkgutil.iter_modules(stk.__path__, prefix="stk."):
        model_module = f"{module.name}.models"
        try:
            importlib.import_module(model_module)
        except ModuleNotFoundError as exc:
            if exc.name != model_module:
                raise


def get_database_url(*, sync: bool = False) -> str:
    """Return the configured database URL, optionally converted for Alembic."""
    database_url = Config.SQLALCHEMY_DATABASE_URI
    if not sync:
        return database_url

    url = make_url(database_url)
    drivername = SYNC_DRIVER_MAP.get(url.drivername)
    if drivername is None:
        return str(url)
    return str(url.set(drivername=drivername))


def get_target_metadata():
    """Return metadata after loading all model modules."""
    import_model_modules()
    return Base.metadata


def build_alembic_config() -> AlembicConfig:
    """Build an Alembic config bound to the current stk settings."""
    config = AlembicConfig(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIR))
    config.set_main_option("sqlalchemy.url", get_database_url(sync=True))
    return config
