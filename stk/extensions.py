"""Extensions module. Each extension is initialized in the app factory located
in app.py
"""

from quart_session import Session
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# SQLite batch migrations can only add or drop named constraints; without a
# convention autogenerate emits None and the upgrade fails half-applied.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


engine = None
async_session_factory = None
session = Session()
