# stk Patterns Reference

## Full Blueprint Example

```python
# stk/products/models.py
import dataclasses
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Boolean, Text
from sqlalchemy.orm import relationship
from stk.extensions import Base

@dataclasses.dataclass
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    products = relationship("Product", back_populates="category", lazy="selectin")

    def to_dict(self):
        return {"id": self.id, "name": self.name}

    def from_dict(self, data):
        self.name = data.get("name", self.name)
        return self

@dataclasses.dataclass
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    price = Column(Numeric(10, 2), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"))
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    category = relationship("Category", back_populates="products", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "price": float(self.price) if self.price else None,
            "category": self.category.to_dict() if self.category else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "active": self.active,
        }

    async def from_dict(self, data):
        self.name = data.get("name", self.name)
        self.description = data.get("description", self.description)
        self.price = data.get("price", self.price)
        self.category_id = data.get("category_id", self.category_id)
        self.active = data.get("active", self.active)
        return self
```

```python
# stk/products/views.py
import logging
import orjson as json
from quart import Blueprint, Response, g, render_template, request
from quart_security import auth_required, current_user, roles_required
from sqlalchemy import func, select
from stk.user.models import Activity
from .models import Product, Category

log = logging.getLogger(__name__)
bp = Blueprint("products", __name__)
PER_PAGE = 25

@bp.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass

@bp.get("/products/")
async def products_page():
    return await render_template("cms/products.html")

@bp.get("/api/products")
async def list_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE, type=int)

    query = select(Product)

    if search := request.args.get("search"):
        query = query.where(Product.name.ilike(f"%{search}%"))
    if category_id := request.args.get("category_id", type=int):
        query = query.where(Product.category_id == category_id)

    count_result = await g.db_session.execute(select(func.count()).select_from(Product))
    total = count_result.scalar()

    result = await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )
    items = [p.to_dict() for p in result.scalars().all()]

    response_data = {"items": items, "total": total, "perPage": per_page}
    return Response(json.dumps(response_data), content_type="application/json")

@bp.post("/api/product/")
async def create_product():
    json_data = await request.json
    product_data = json_data.get("item", {})
    if not product_data.get("name"):
        return {"message": "Name is required"}, 400
    product = Product()
    await product.from_dict(product_data)
    g.db_session.add(product)
    try:
        await g.db_session.flush()
        await Activity.register(current_user.id, "Product Create", product.to_dict())
        await g.db_session.commit()
        return {"message": "Product successfully created!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error creating product")
        return {"message": "Error creating product"}, 412

@bp.post("/api/product/<int:id>")
async def update_product(id):
    product = await g.db_session.get(Product, id)
    if product is None:
        return {"message": "Product not found"}, 404
    json_data = await request.json
    product_data = json_data.get("item", {})
    old_data = product.to_dict()
    try:
        await product.from_dict(product_data)
        await Activity.register(
            current_user.id, "Product Update",
            {"old": old_data, "new": product.to_dict()},
        )
        await g.db_session.commit()
        return {"message": "Product successfully updated!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error updating product")
        return {"message": "Error updating product"}, 412

@bp.route("/api/product/<int:id>", methods=["DELETE"])
async def delete_product(id):
    product = await g.db_session.get(Product, id)
    if product is None:
        return {"message": "Product not found"}, 404
    product_data = product.to_dict()
    try:
        await g.db_session.delete(product)
        await Activity.register(current_user.id, "Product Delete", product_data)
        await g.db_session.commit()
        return {"message": "Product successfully deleted!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error deleting product")
        return {"message": "Error deleting product"}, 412

@bp.get("/api/categories")
async def list_categories():
    result = await g.db_session.execute(select(Category))
    return {"items": [c.to_dict() for c in result.scalars().all()]}
```

## Search and Filtering

```python
from sqlalchemy import select, func, or_

@bp.get("/api/products")
async def list_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE, type=int)

    query = select(Product)

    if search := request.args.get("search"):
        query = query.where(or_(
            Product.name.ilike(f"%{search}%"),
            Product.description.ilike(f"%{search}%"),
        ))

    if category_id := request.args.get("category_id", type=int):
        query = query.where(Product.category_id == category_id)

    if min_price := request.args.get("min_price", type=float):
        query = query.where(Product.price >= min_price)
    if max_price := request.args.get("max_price", type=float):
        query = query.where(Product.price <= max_price)

    if active := request.args.get("active"):
        query = query.where(Product.active == (active.lower() == "true"))

    sort_by = request.args.get("sort_by", "id")
    sort_order = request.args.get("sort_order", "asc")
    column = getattr(Product, sort_by, Product.id)
    query = query.order_by(column.desc() if sort_order == "desc" else column.asc())

    count_result = await g.db_session.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    result = await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )
    items = [p.to_dict() for p in result.scalars().all()]

    response_data = {"items": items, "total": total, "perPage": per_page}
    return Response(json.dumps(response_data), content_type="application/json")
```

## File Uploads

```python
from quart import current_app
from werkzeug.utils import secure_filename

@bp.post("/api/product/<int:id>/image")
async def upload_image(id):
    product = await g.db_session.get(Product, id)
    if not product:
        return {"message": "Not found"}, 404
    files = await request.files
    file = files.get("image")
    if file:
        filename = secure_filename(file.filename)
        path = current_app.config["UPLOAD_FOLDER"] / filename
        await file.save(path)
        product.image = filename
        await g.db_session.commit()
    return {"item": product.to_dict()}
```

## Join Queries (Activity + User example)

When you need data from related tables without a relationship:

```python
result = await g.db_session.execute(
    select(Activity, User)
    .outerjoin(User, Activity.user_id == User.id)
    .order_by(Activity.created_at.desc())
    .offset((page - 1) * per_page)
    .limit(per_page)
)

items = []
for activity, user in result.all():
    items.append({
        "id": activity.id,
        "user": user.display_name if user else f"User ID: {activity.user_id}",
        "action": activity.action,
        "data": activity.data,
        "created_at": activity.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })
```

## Vue CRUD Template (Options API)

Complete template with data table, edit dialog, delete confirmation, and snackbar:

```html
{% extends "layout.html" %}
{% block content %}
<v-card class="ma-2 mt-12 w-100 h-100">
    <v-toolbar>
        <v-toolbar-title>Products</v-toolbar-title>
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
                    <v-btn class="ml-auto" @click="createItem" size="small" color="primary" variant="elevated">
                        <template v-slot:prepend><i class="ti ti-plus"></i></template>
                        Add Product
                    </v-btn>
                </v-toolbar>
            </template>

            <template v-slot:item.active="{ item }">
                <v-avatar size="16" :color="item.active ? 'green' : 'grey'"></v-avatar>
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
            <v-toolbar-title>Product Editor</v-toolbar-title>
            <template v-slot:append>
                <v-btn @click="edialog=false" size="small" icon="ti ti-x" variant="text"></v-btn>
            </template>
        </v-toolbar>
        <v-card-text>
            <v-text-field label="Name" v-model="eitem.name"></v-text-field>
            <v-textarea label="Description" v-model="eitem.description"></v-textarea>
            <v-text-field label="Price" type="number" v-model="eitem.price"></v-text-field>
            <v-switch color="primary" label="Active" v-model="eitem.active"></v-switch>
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
<!-- Server data (optional, for dropdowns etc.) -->
<script type="application/json" id="categories-data">
{{ categories|tojson|safe }}
</script>

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
                {title: 'Price', value: 'price'},
                {title: 'Active', value: 'active', sortable: false},
                {title: 'Actions', value: 'actions', sortable: false}
            ],
            edialog: false,
            eitem: { id: "", name: "", description: "", price: 0, active: true },
            categories: JSON.parse(document.querySelector('#categories-data').textContent),
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
            axios.get(`/api/products?page=${this.options.page}&per_page=${this.options.itemsPerPage}`)
                .then(res => {
                    this.items = res.data.items;
                    this.itemsLength = res.data.total;
                })
                .catch(error => this.showSnack('Failed to load products'));
        },
        createItem() {
            this.eitem = { name: "", description: "", price: 0, active: true };
            this.edialog = true;
        },
        editItem(item) {
            this.eitem = toRaw(item);
            this.$nextTick(() => { this.edialog = true; });
        },
        saveItem() {
            const url = this.eitem.id
                ? `/api/product/${this.eitem.id}`
                : '/api/product/';
            axios.post(url, {item: this.eitem})
                .then(res => { this.showSnack(res.data?.message); this.refresh(); })
                .catch(err => this.showSnack(err.response?.data?.message || 'Error'));
            this.edialog = false;
        },
        deleteItem(item) {
            if (confirm('Are you sure?')) {
                axios.delete(`/api/product/${item.id}`)
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

## Error Handling

API endpoints return `{"message": "..."}` on errors with try/except rollback:

```python
@bp.post("/api/product/")
async def create_product():
    json_data = await request.json
    product_data = json_data.get("item", {})
    if not product_data.get("name"):
        return {"message": "Name is required"}, 400
    product = Product()
    await product.from_dict(product_data)
    g.db_session.add(product)
    try:
        await g.db_session.flush()
        await Activity.register(current_user.id, "Product Create", product.to_dict())
        await g.db_session.commit()
        return {"message": "Product successfully created!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error creating product")
        return {"message": "Error creating product"}, 412
```

Global error handler in `app.py` catches unhandled exceptions, rolls back the session, and returns JSON for API requests or renders an error template otherwise.

## WebSocket Broadcasting

Activity.register() auto-broadcasts via WebSocket. For custom broadcasts:

```python
from stk.websocket import broadcast

# Broadcast to all connected users
await broadcast({"type": "notification", "text": "Something happened"})

# Broadcast to specific user
await broadcast({"type": "update", "data": {...}}, user_id=123)
```

The layout's `_onWsMessage` handler receives these. Extend it for custom message types.
