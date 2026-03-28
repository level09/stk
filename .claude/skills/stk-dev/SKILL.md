---
name: stk-dev
description: |
  Background knowledge for stk async Quart framework development. Auto-loads when working on stk-based code: models, views, templates, database queries, auth patterns, Vue frontend. Provides conventions, patterns, and gotchas so Claude writes correct async Quart code instead of Flask patterns.
user-invocable: false
---

# stk Framework Conventions

Async Quart + SQLAlchemy 2.x async + quart-security + Vue 3/Vuetify 3 (Options API). No build step.

## Critical Rules

- ALL route handlers are `async def`. ALL DB operations use `await`.
- DB sessions via `g.db_session` (request-scoped), NOT a global `db` object.
- Models inherit from `Base` (plain DeclarativeBase), NOT `db.Model`.
- Imports: `from quart import ...`, NOT `from flask import ...`.
- Auth: `from quart_security import ...`, NOT `from flask_security import ...`.
- Relationships MUST use `lazy="selectin"` for async compatibility.
- Vue delimiters are `${}`, NOT `{{}}` (conflicts with Jinja). Access via `config.delimiters`.
- Vue uses **Options API** (`data()`, `methods`, `mounted()`), NOT Composition API.
- No Celery. Background tasks via `stk.tasks.run_in_background()`.
- Pagination is manual: `offset().limit()` + `select(func.count())`.
- Icons: Tabler Icons (`ti ti-*`), NOT Material Design Icons.
- JSON serialization for list endpoints: `orjson` via `import orjson as json`.
- Frontend sends mutations wrapped: `{item: {...}}`, extract with `json_data.get("item", {})`.

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

Two patterns exist:

```python
# Pattern 1: Blueprint-level auth (preferred for admin sections)
# Protects ALL routes in the blueprint
@bp.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass

@bp.get("/things/")
async def things_page():
    ...  # already protected by before_request

# Pattern 2: Per-route auth (for mixed-access blueprints)
from quart_security import auth_required, roles_required, current_user

@bp.get("/protected")
@auth_required("session")
async def protected():
    ...
```

## Model Patterns

Models use `@dataclasses.dataclass` decorator and inherit from Base:

```python
import dataclasses
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import relationship
from stk.extensions import Base

@dataclasses.dataclass
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

    # Instance method that mutates self (NOT a classmethod that returns new instance)
    async def from_dict(self, data):
        self.name = data.get("name", self.name)
        self.active = data.get("active", self.active)
        return self
```

## Async API Endpoint Pattern

```python
import logging
import orjson as json
from quart import Blueprint, Response, g, render_template, request
from quart_security import auth_required, current_user, roles_required
from sqlalchemy import func, select
from stk.user.models import Activity
from .models import Thing

log = logging.getLogger(__name__)
bp = Blueprint("things", __name__)
PER_PAGE = 25

# Blueprint-level auth (all routes require admin)
@bp.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass

# Page route
@bp.get("/things/")
async def things_page():
    return await render_template("things/index.html")

# List with pagination
@bp.get("/api/things")
async def list_things():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE, type=int)

    query = select(Thing)
    if search := request.args.get("search"):
        query = query.where(Thing.name.ilike(f"%{search}%"))

    count_result = await g.db_session.execute(select(func.count()).select_from(Thing))
    total = count_result.scalar()

    result = await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )
    items = [t.to_dict() for t in result.scalars().all()]

    response_data = {"items": items, "total": total, "perPage": per_page}
    return Response(json.dumps(response_data), content_type="application/json")

# Create (frontend sends {item: {...}})
@bp.post("/api/thing/")
async def create_thing():
    json_data = await request.json
    thing_data = json_data.get("item", {})
    thing = Thing()
    await thing.from_dict(thing_data)
    g.db_session.add(thing)
    try:
        await g.db_session.flush()
        await Activity.register(current_user.id, "Thing Create", thing.to_dict())
        await g.db_session.commit()
        return {"message": "Thing successfully created!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error creating thing")
        return {"message": "Error creating thing"}, 412

# Update (POST, not PUT)
@bp.post("/api/thing/<int:id>")
async def update_thing(id):
    thing = await g.db_session.get(Thing, id)
    if thing is None:
        return {"message": "Thing not found"}, 404
    json_data = await request.json
    thing_data = json_data.get("item", {})
    old_data = thing.to_dict()
    try:
        await thing.from_dict(thing_data)
        await Activity.register(
            current_user.id, "Thing Update",
            {"old": old_data, "new": thing.to_dict()},
        )
        await g.db_session.commit()
        return {"message": "Thing successfully updated!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error updating thing")
        return {"message": "Error updating thing"}, 412

# Delete
@bp.route("/api/thing/<int:id>", methods=["DELETE"])
async def delete_thing(id):
    thing = await g.db_session.get(Thing, id)
    if thing is None:
        return {"message": "Thing not found"}, 404
    thing_data = thing.to_dict()
    try:
        await g.db_session.delete(thing)
        await Activity.register(current_user.id, "Thing Delete", thing_data)
        await g.db_session.commit()
        return {"message": "Thing successfully deleted!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error deleting thing")
        return {"message": "Error deleting thing"}, 412
```

## Activity Logging

Always log admin/mutation actions. Async, broadcasts to WebSocket:
```python
await Activity.register(current_user.id, "Action Name", {"key": "value"})
```

## Vue Frontend Pattern (Options API)

Templates use Options API with `layoutMixin`, `config.delimiters`, and `registerStkComponents`:

```html
{% extends "layout.html" %}
{% block content %}
<v-card class="ma-2 mt-12 w-100 h-100">
  <v-toolbar>
    <v-toolbar-title>Things</v-toolbar-title>
    <v-spacer></v-spacer>
  </v-toolbar>
  <v-card-text>
    <v-data-table-server
      :items="items" :items-length="itemsLength"
      :headers="headers"
      :page="options.page" :items-per-page="options.itemsPerPage"
      @update:options="refresh" hover
    >
      <template v-slot:top>
        <v-toolbar dense elevation="0" color="transparent">
          <v-btn class="ml-auto" @click="createItem" size="small" color="primary">
            <template v-slot:prepend><i class="ti ti-plus"></i></template>
            Add Thing
          </v-btn>
        </v-toolbar>
      </template>
      <template v-slot:item.actions="{ item }">
        <v-icon small class="mr-2" @click="editItem(item)">ti ti-pencil</v-icon>
        <v-icon small @click="deleteItem(item)">ti ti-trash</v-icon>
      </template>
    </v-data-table-server>
  </v-card-text>
</v-card>

<!-- Edit Dialog -->
<v-dialog v-model="edialog" width="660">
  <v-card v-if="edialog">
    <v-toolbar>
      <v-toolbar-title>Thing Editor</v-toolbar-title>
      <template v-slot:append>
        <v-btn @click="edialog=false" size="small" icon="ti ti-x" variant="text"></v-btn>
      </template>
    </v-toolbar>
    <v-card-text>
      <v-text-field label="Name" v-model="eitem.name"></v-text-field>
    </v-card-text>
    <v-card-actions>
      <v-spacer></v-spacer>
      <v-btn color="primary" @click="saveItem" variant="elevated">Save</v-btn>
    </v-card-actions>
  </v-card>
</v-dialog>

<v-snackbar v-model="snackBar" rounded="pill" elevation="25">
  ${snackMessage}
  <template v-slot:actions>
    <v-btn @click="snackBar=false" icon="ti ti-x" size="small" variant="text"></v-btn>
  </template>
</v-snackbar>
{% endblock %}

{% block js %}
<script>
const {createApp, toRaw} = Vue;
const {createVuetify} = Vuetify;
const vuetify = createVuetify(config.vuetifyConfig);

window.app = createApp({
  mixins: [layoutMixin],
  delimiters: config.delimiters,
  data() {
    return {
      snackBar: false,
      snackMessage: "",
      items: [],
      itemsLength: 0,
      options: { page: 1, itemsPerPage: 25 },
      headers: [
        {title: 'ID', value: 'id'},
        {title: 'Name', value: 'name'},
        {title: 'Actions', value: 'actions', sortable: false}
      ],
      edialog: false,
      eitem: { id: "", name: "" }
    };
  },
  methods: {
    showSnack(message) {
      this.snackMessage = message;
      this.snackBar = true;
    },
    refresh(options) {
      if (options) {
        this.options = { ...this.options, page: options.page, itemsPerPage: options.itemsPerPage };
      }
      axios.get(`/api/things?page=${this.options.page}&per_page=${this.options.itemsPerPage}`)
        .then(res => {
          this.items = res.data.items;
          this.itemsLength = res.data.total;
        })
        .catch(error => this.showSnack('Failed to load'));
    },
    createItem() {
      this.eitem = {};
      this.edialog = true;
    },
    editItem(item) {
      this.eitem = toRaw(item);
      this.$nextTick(() => { this.edialog = true; });
    },
    saveItem() {
      const url = this.eitem.id ? `/api/thing/${this.eitem.id}` : '/api/thing/';
      axios.post(url, {item: this.eitem})
        .then(res => { this.showSnack(res.data?.message); this.refresh(); })
        .catch(err => this.showSnack(err.response?.data?.message || 'Error'));
      this.edialog = false;
    },
    deleteItem(item) {
      if (confirm('Are you sure?')) {
        axios.delete(`/api/thing/${item.id}`)
          .then(res => { this.showSnack(res.data?.message); this.refresh(); })
          .catch(err => this.showSnack(err.response?.data));
      }
    }
  }
});

registerStkComponents(app);
app.use(vuetify).mount("#app");
</script>
{% endblock %}
```

## Passing Server Data to Vue

Use `<script type="application/json">` tags parsed in `data()`:

```html
<!-- In template body -->
<script type="application/json" id="roles-data">
{{ roles|tojson|safe }}
</script>

<!-- In Vue script -->
data() {
  return {
    roles: JSON.parse(document.querySelector('#roles-data').textContent),
  };
}
```

## Navigation Sidebar

Add entries in `stk/static/js/navigation.js`. Items support role-based visibility via `role` (singular string). Supports nested `children` for grouped items:
```javascript
// Simple link (visible to all)
{ title: 'Dashboard', icon: 'ti ti-home', to: '/dashboard' },

// Section heading
{ heading: 'Administration' },

// Admin-only link
{ title: 'Activity Logs', icon: 'ti ti-history', to: '/activities', role: 'admin' },

// Grouped with children
{
  title: 'User Management', icon: 'ti ti-users-group', role: 'admin',
  children: [
    { title: 'Users', icon: 'ti ti-users', to: '/users' },
    { title: 'Roles', icon: 'ti ti-shield', to: '/roles' },
  ]
},
```

## Template Block Structure

```html
{% extends "layout.html" %}
{% block css %}<!-- extra CSS -->{% endblock %}
{% block content %}<!-- Vuetify components -->{% endblock %}
{% block js %}<!-- Vue app script -->{% endblock %}
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
