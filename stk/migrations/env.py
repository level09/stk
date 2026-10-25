from __future__ import annotations

import logging

from alembic import context
from sqlalchemy import engine_from_config, pool

from stk.migrations import get_target_metadata, include_object

config = context.config

if not config.attributes.get("quiet"):
    logging.basicConfig(format="%(levelname)-5.5s [%(name)s] %(message)s")
    logging.getLogger("alembic").setLevel(logging.INFO)

target_metadata = get_target_metadata()
url = config.get_main_option("sqlalchemy.url")


def run_migrations_offline() -> None:
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
        render_as_batch=url.startswith("sqlite"),
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        {"sqlalchemy.url": url}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            # SQLite alters tables by copying them; batch mode does that for us.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
