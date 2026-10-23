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
result = await g.db_session.execute(
    select(Post).where(Post.title.like("%python%"))
)
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
uv run stk db revision -m "add post"   # Autogenerate a revision
uv run stk db upgrade                  # Apply it
uv run stk db check                    # Fail if models drifted from migrations
uv run stk db downgrade -1             # Roll back one step
```

`stk verify` runs the drift check too, so a model change without a migration fails the gate. Config lives in `stk/migrations.py`, the Alembic env in `alembic/env.py`, and revisions in `alembic/versions/`.

## SQLite traps

SQLite runs migrations in batch mode automatically, which makes `ALTER TABLE` work. Three traps remain:

- DDL is not transactional. A failed upgrade leaves the tables it already created: fix the revision, drop only those new empty tables, and upgrade again.
- A new NOT NULL column on a table with rows needs a `server_default` in both the migration and the model, or the upgrade fails.
- Constraints are named by the convention on `Base.metadata` in `stk/extensions.py`. Keep it: batch mode cannot add an unnamed foreign key.
