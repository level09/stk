---
name: stk-dev
description: |
  Background knowledge for stk async Quart framework development. Auto-loads when working on stk-based code: models, views, templates, database queries, auth patterns, Vue frontend. Provides conventions, patterns, and gotchas so Claude writes correct async Quart code instead of Flask patterns.
user-invocable: false
---

# stk Framework Conventions

Async Quart + SQLAlchemy 2.x async + quart-security + Vue 3/Vuetify 3. No build step.

## Critical Rules

- ALL route handlers are `async def`. ALL DB operations use `await`.
- DB sessions via `g.db_session` (request-scoped), NOT a global `db` object.
- Models inherit from `Base` (plain DeclarativeBase), NOT `db.Model`.
- Imports: `from quart import ...`, NOT `from flask import ...`.
- Auth: `from quart_security import ...`, NOT `from flask_security import ...`.
- Relationships MUST use `lazy="selectin"` for async compatibility.
- Vue delimiters are `${}`, NOT `{{}}` (conflicts with Jinja).
- No Celery. Background tasks via `stk.tasks.run_in_background()`.
- Pagination is manual: `offset().limit()` + `select(func.count())`.

## DB Access Patterns

```python
# In request handlers
from quart import g
from sqlalchemy import select, func

result = await g.db_session.execute(select(Model).where(Model.active == True))
items = result.scalars().all()
item = await g.db_session.get(Model, id)
total = await g.db_session.scalar(select(func.count()).select_from(Model))

# In CLI commands (no request context)
import stk.extensions as ext
async with ext.async_session_factory() as session:
    ...
```

## Auth Decorators

```python
from quart_security import auth_required, roles_required, current_user

@bp.get("/protected")
@auth_required("session")
async def protected():
    ...

@bp.get("/admin-only")
@auth_required("session")
@roles_required("admin")
async def admin_only():
    ...
```

## Model Pattern

```python
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import relationship
from stk.extensions import Base

class Thing(Base):
    __tablename__ = "things"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    user_id = Column(Integer, ForeignKey("user.id"))

    user = relationship("User", lazy="selectin")

    def to_dict(self):
        return {"id": self.id, "name": self.name, "active": self.active}

    @classmethod
    async def from_dict(cls, data):
        return cls(name=data["name"], active=data.get("active", True))
```

## Async API Endpoint Pattern

```python
from quart import Blueprint, g, request
from quart_security import auth_required, roles_required, current_user
from sqlalchemy import select, func
from stk.user.models import Activity

bp = Blueprint("things", __name__, url_prefix="/api")

@bp.get("/things")
@auth_required("session")
async def list_things():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    query = select(Thing)

    if search := request.args.get("search"):
        query = query.where(Thing.name.ilike(f"%{search}%"))

    total = await g.db_session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()

    return {"items": [t.to_dict() for t in items], "total": total, "perPage": per_page}

@bp.post("/thing/")
@auth_required("session")
async def create_thing():
    data = await request.json
    thing = await Thing.from_dict(data)
    g.db_session.add(thing)
    await g.db_session.flush()
    await Activity.register(current_user.id, "Thing Create", thing.to_dict())
    await g.db_session.commit()
    return {"item": thing.to_dict()}
```

## Activity Logging

Always log admin/mutation actions. Async, broadcasts to WebSocket:
```python
await Activity.register(current_user.id, "Action Name", {"key": "value"})
```

## Vue Frontend Pattern

```html
{% extends "layout.html" %}
{% block content %}
<div id="app">
  <v-data-table-server
    :headers="headers" :items="items" :items-length="total"
    :loading="loading" @update:options="loadItems"
  ></v-data-table-server>
</div>
{% endblock %}

{% block js %}
<script>
const { createApp, ref } = Vue;
createApp({
  delimiters: ['${', '}'],
  setup() {
    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    // ... fetch from /api/things
    return { items, total, loading };
  }
}).use(createVuetify(vuetifyConfig)).mount('#app');
</script>
{% endblock %}
```

## Background Tasks

```python
from stk.tasks import run_in_background, run_with_session

await run_in_background(send_notification(user_id))

async def heavy_work(session):
    item = await session.get(Model, item_id)
    item.status = "processed"
await run_with_session(heavy_work)
```

For detailed examples see [references/patterns.md](references/patterns.md).
