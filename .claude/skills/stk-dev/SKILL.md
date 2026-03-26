---
name: stk-dev
description: |
  Development skill for stk async Quart framework. Use when implementing features, fixing bugs, or writing code for stk-based applications. This includes creating blueprints, models, async API endpoints, Vue.js/Vuetify frontend components, database operations, or migrations. Triggers: creating blueprints, adding models, building APIs, Vue/Vuetify components, background tasks, database migrations.
---

# stk Development

Async Quart + Vue 3 + Vuetify 3 framework. No build step. SQLAlchemy 2.x async. quart-security auth.

## Quick Reference

```bash
uv run quart run --port 5001      # Dev server (5001 on macOS)
uv run quart create-db            # Apply all Alembic migrations
uv run quart install              # Create admin user
uv run quart db revision -m "desc" # Generate migration
uv run ruff check --fix . && uv run ruff format .
```

## Blueprint Structure

```
stk/
  feature_name/
    views.py      # Async routes and API endpoints
    models.py     # SQLAlchemy models (inherit from Base)
  templates/
    feature_name/ # Jinja templates
```

Register in `app.py`:
```python
from stk.feature_name.views import bp as feature_bp
app.register_blueprint(feature_bp)
```

## Models

Inherit from `Base`, not `db.Model`. Use `Column` from sqlalchemy directly. All relationships must use `lazy="selectin"` for async.

```python
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Boolean
from sqlalchemy.orm import relationship
from stk.extensions import Base

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    price = Column(Numeric(10, 2))
    category_id = Column(Integer, ForeignKey("categories.id"))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    category = relationship("Category", back_populates="products", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": float(self.price) if self.price else None,
            "category": self.category.to_dict() if self.category else None,
            "active": self.active,
        }

    @classmethod
    async def from_dict(cls, data):
        return cls(
            name=data.get("name"),
            price=data.get("price"),
            category_id=data.get("category_id"),
            active=data.get("active", True),
        )
```

## API Endpoints

All handlers are async. Use `g.db_session` for DB access. Manual pagination with `offset().limit()`.

```python
from quart import Blueprint, g, request
from quart_security import auth_required, roles_required, current_user
from sqlalchemy import select, func
from stk.user.models import Activity
from .models import Product

bp = Blueprint("products", __name__, url_prefix="/api")

@bp.get("/products")
@auth_required("session")
@roles_required("admin")
async def list_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    query = select(Product)

    if search := request.args.get("search"):
        query = query.where(Product.name.ilike(f"%{search}%"))

    total = await g.db_session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()

    return {"items": [p.to_dict() for p in items], "total": total, "perPage": per_page}

@bp.post("/product/")
@auth_required("session")
@roles_required("admin")
async def create_product():
    data = await request.json
    product = await Product.from_dict(data)
    g.db_session.add(product)
    await g.db_session.flush()
    await Activity.register(current_user.id, "Product Create", product.to_dict())
    await g.db_session.commit()
    return {"item": product.to_dict()}

@bp.post("/product/<int:id>")
@auth_required("session")
@roles_required("admin")
async def update_product(id):
    product = await g.db_session.get(Product, id)
    if not product:
        return {"message": "Not found"}, 404
    data = await request.json
    old = product.to_dict()
    product.name = data.get("name", product.name)
    product.price = data.get("price", product.price)
    await Activity.register(current_user.id, "Product Update", {"old": old, "new": product.to_dict()})
    await g.db_session.commit()
    return {"item": product.to_dict()}

@bp.delete("/product/<int:id>")
@auth_required("session")
@roles_required("admin")
async def delete_product(id):
    product = await g.db_session.get(Product, id)
    if not product:
        return {"message": "Not found"}, 404
    await Activity.register(current_user.id, "Product Delete", product.to_dict())
    await g.db_session.delete(product)
    await g.db_session.commit()
    return {"deleted": True}
```

## Database Queries

```python
from sqlalchemy import select, func, or_

# Select with filter
result = await g.db_session.execute(select(Product).where(Product.active == True))
products = result.scalars().all()

# Get by ID
product = await g.db_session.get(Product, id)

# Count
total = await g.db_session.scalar(select(func.count()).select_from(Product))

# Search across fields
query = select(Product).where(or_(
    Product.name.ilike(f"%{search}%"),
    Product.description.ilike(f"%{search}%"),
))

# Join
query = select(Product).join(Category).where(Category.name == "Electronics")

# Manual pagination
query = select(Product).offset((page - 1) * per_page).limit(per_page)
```

## Model Relationships

```python
# One-to-many (always lazy="selectin" for async)
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    products = relationship("Product", back_populates="category", lazy="selectin")

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, ForeignKey("categories.id"))
    category = relationship("Category", back_populates="products", lazy="selectin")

# Many-to-many
product_tags = Table(
    "product_tags", Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)

class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    tags = relationship("Tag", secondary=product_tags, backref="products", lazy="selectin")
```

## Activity Logging

Always log admin actions. `Activity.register()` is async and broadcasts to WebSocket:

```python
from stk.user.models import Activity

await Activity.register(current_user.id, "Action Name", {"relevant": "data"})
```

## Background Tasks

No Celery. Fire-and-forget via asyncio:

```python
from stk.tasks import run_in_background, run_with_session

# Simple async task
await run_in_background(send_notification(user_id))

# Task that needs its own DB session
async def process_order(session):
    order = await session.get(Order, order_id)
    order.status = "processed"

await run_with_session(process_order)
```

## Vue 3 + Vuetify Frontend

Uses `${}` delimiters (not `{{}}`). Mount per-page Vue apps:

```html
{% extends "layout.html" %}
{% block content %}
<div id="app">
  <v-data-table-server
    :headers="headers"
    :items="items"
    :items-length="total"
    :loading="loading"
    @update:options="loadItems"
  >
    <template v-slot:item.actions="{ item }">
      <v-btn icon size="small" @click="editItem(item)">
        <v-icon>mdi-pencil</v-icon>
      </v-btn>
      <v-btn icon size="small" color="error" @click="deleteItem(item)">
        <v-icon>mdi-delete</v-icon>
      </v-btn>
    </template>
  </v-data-table-server>
</div>
{% endblock %}

{% block js %}
<script>
const { createApp, ref } = Vue;
const { createVuetify } = Vuetify;

createApp({
  delimiters: ['${', '}'],
  setup() {
    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const headers = ref([
      { title: 'Name', key: 'name' },
      { title: 'Price', key: 'price' },
      { title: 'Actions', key: 'actions', sortable: false }
    ]);

    async function loadItems({ page, itemsPerPage }) {
      loading.value = true;
      const res = await axios.get('/api/products', { params: { page, per_page: itemsPerPage } });
      items.value = res.data.items;
      total.value = res.data.total;
      loading.value = false;
    }

    return { items, total, loading, headers, loadItems };
  }
}).use(createVuetify(vuetifyConfig)).mount('#app');
</script>
{% endblock %}
```

## Migrations

```bash
# After changing models, generate a migration
uv run quart db revision -m "add products table"

# Apply
uv run quart db upgrade

# Rollback
uv run quart db downgrade -1
```

For patterns reference, see [references/patterns.md](references/patterns.md).
