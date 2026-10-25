---
title: "Models and Migrations"
description: "Async SQLAlchemy models, queries, and Alembic migrations"
---

stk uses async SQLAlchemy 2. There is no `db` object: models inherit from `Base` in `stk/extensions.py`, request handlers use `g.db_session`, and everything else opens a session from `stk.extensions.async_session_factory`.

## Defining a model

This is the shape `stk new` generates:

```python
import dataclasses
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship
from stk.extensions import Base


@dataclasses.dataclass
class Post(Base):
    __tablename__ = "post"

    id = Column(Integer, primary_key=True)
    title = Column(String(80), nullable=False)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"))
    user = relationship("User", lazy="selectin")

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "content": self.content}

    async def from_dict(self, data: dict) -> "Post":
        self.title = data.get("title", self.title)
        self.content = data.get("content", self.content)
        return self
```

`to_dict()` is what list endpoints serialize. `from_dict()` is an async instance method that updates the row in place, so create and update share it.

Every relationship must use `lazy="selectin"`. Selectin loads only on query, so reading `post.user` on a row you just `add()`ed raises `MissingGreenlet`. Load it with `await g.db_session.get(Post, post.id)` or a query first.

`Base` sets `eager_defaults`, so columns filled by a `server_default` or a SQL `onupdate` (`func.now()`) are fetched during the flush. A model that sets its own `__mapper_args__` replaces that; keep `"eager_defaults": True` in it, or reading such a column after a flush raises `MissingGreenlet`.

## Queries

```python
from quart import g
from sqlalchemy import select

# Create
post = Post(title="New Post", content="Content here")
g.db_session.add(post)
await g.db_session.commit()

# Query
result = await g.db_session.execute(select(Post))
posts = result.scalars().all()

# Get by ID
post = await g.db_session.get(Post, 1)

# Filtered query
result = await g.db_session.execute(select(Post).where(Post.title.like("%python%")))
posts = result.scalars().all()

# Update
post.title = "Updated Title"
await g.db_session.commit()

# Delete
await g.db_session.delete(post)
await g.db_session.commit()
```

To read two tables without a relationship, select both and join:

```python
result = await g.db_session.execute(
    select(Activity, User)
    .outerjoin(User, Activity.user_id == User.id)
    .order_by(Activity.created_at.desc())
)
for activity, user in result.all():
    ...
```

Outside a request, open a session yourself:

```python
import stk.extensions as ext

async with ext.async_session_factory() as session:
    posts = (await session.execute(select(Post))).scalars().all()
```

To see SQL as it runs, raise the engine logger: `logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)`. To poke at data interactively, use [the shell](/shell).

## Migrations

Schema changes go through Alembic. After changing a model:

```bash
uv run stk db revision -m "add post"   # Autogenerate a revision in the app's lineage
uv run stk db upgrade                  # Apply stk's migrations and the app's
uv run stk db check                    # Fail if models drifted from migrations
uv run stk db downgrade -1             # Roll back one step
```

There are two lineages and one version table. stk's revisions ship inside the package (`stk/migrations/versions/`) under the branch label `stk`. The app's live in `myapp/migrations/` under its package name as branch label: the first `stk db revision` starts that branch. Every app revision records `depends_on` stk's head at the time it was written, so core tables such as `user` exist before an app table points at them. `stk db upgrade` runs `upgrade heads`, so a new stk release and new app revisions apply in one command, and an app never merges heads by hand.

`stk verify` runs the drift check too, so a model change without a migration fails the gate. The check migrates a throwaway database of the configured dialect (Postgres needs a role with CREATEDB), because SQLite cannot render Postgres types. It also fails on a revision whose `upgrade()` drops or renames a table or column, retypes a column, or adds a NOT NULL column without a `server_default`. Autogenerate writes a renamed field as a drop plus an add, which loses the data. When a destructive step is intended, say so with a `# destructive: <reason>` comment inside `upgrade()`. The Alembic env lives in `stk/migrations/env.py`, built in code; apps need no `alembic.ini`.

`stk db revision` imports the module of every column type Alembic writes by its path, such as `pgvector.sqlalchemy.halfvec.HALFVEC` or a `UserDefinedType` of your own, then sorts the revision's imports and formats it with the app's ruff config, so the revision runs and passes `ruff check`.

Alembic autogenerate leaves out a `CheckConstraint` passed to a single column (`mapped_column(Integer, CheckConstraint("rank > 0"))`), and the drift check cannot see it either: the revision creates the column without the check. Declare checks at table level, which autogenerate does write:

```python
class Place(Base):
    __tablename__ = "place"
    __table_args__ = (CheckConstraint("rank > 0", name="rank_positive"),)
```

Or add the check to the revision by hand. `stk db revision` warns about each column-level check in the columns it adds.

A test that needs a migrated database builds the same config in code. `build_alembic_config` takes the app, or its import name plus a URL, so a test can migrate a throwaway database before it builds its app:

```python
from alembic import command
from stk.migrations import build_alembic_config, throwaway_database_url

with throwaway_database_url(Config.SQLALCHEMY_DATABASE_URI, sync=True) as url:
    command.upgrade(build_alembic_config("myapp", url, quiet=True), "heads")
```

A Postgres extension (PostGIS, pgvector) must exist before a non-superuser role migrates: create it as the superuser, as the app's `postgres/init-db.sh` notes. Autogenerate never offers to drop `spatial_ref_sys`, the table PostGIS owns. Mark a model table that needs PostGIS with `info={"postgis": True}`, and `stk.migrations.portable_tables()` leaves it out when tests build tables on SQLite.

## SQLite traps

SQLite runs migrations in batch mode automatically, which makes `ALTER TABLE` work. Three traps remain:

- DDL is not transactional. A failed upgrade leaves the tables it already created: fix the revision, drop only those new empty tables, and upgrade again.
- A new NOT NULL column on a table with rows needs a `server_default` in both the migration and the model, or the upgrade fails.
- Constraints are named by the convention on `Base.metadata` in `stk/extensions.py`. Keep it: batch mode cannot add an unnamed foreign key. The convention also applies to names you pass to `op` calls, so `op.create_check_constraint("ck_post_title", ...)` becomes `ck_post_ck_post_title`; wrap a full name in `op.f("ck_post_title")`.
