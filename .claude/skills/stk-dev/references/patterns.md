# stk Patterns Reference

## Full Blueprint Example

```python
# stk/products/models.py
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String, Boolean, Text
from sqlalchemy.orm import relationship
from stk.extensions import Base

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)
    products = relationship("Product", back_populates="category", lazy="selectin")

    def to_dict(self):
        return {"id": self.id, "name": self.name}

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

    @classmethod
    async def from_dict(cls, data):
        return cls(
            name=data.get("name"),
            description=data.get("description"),
            price=data.get("price"),
            category_id=data.get("category_id"),
            active=data.get("active", True),
        )
```

```python
# stk/products/views.py
from quart import Blueprint, g, render_template, request
from quart_security import auth_required, roles_required, current_user
from sqlalchemy import select, func
from stk.user.models import Activity
from .models import Product, Category

bp = Blueprint("products", __name__)

@bp.get("/products/")
@auth_required("session")
async def products_page():
    return await render_template("products/index.html")

@bp.get("/api/products")
@auth_required("session")
@roles_required("admin")
async def list_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

    query = select(Product)

    if search := request.args.get("search"):
        query = query.where(Product.name.ilike(f"%{search}%"))
    if category_id := request.args.get("category_id", type=int):
        query = query.where(Product.category_id == category_id)

    total = await g.db_session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()

    return {"items": [p.to_dict() for p in items], "total": total, "perPage": per_page}

@bp.get("/api/categories")
@auth_required("session")
async def list_categories():
    result = await g.db_session.execute(select(Category))
    return {"items": [c.to_dict() for c in result.scalars().all()]}
```

## Search and Filtering

```python
from sqlalchemy import select, func, or_

@bp.get("/api/products")
@auth_required("session")
@roles_required("admin")
async def list_products():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)

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

    total = await g.db_session.scalar(select(func.count()).select_from(query.subquery()))
    items = (await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )).scalars().all()

    return {"items": [p.to_dict() for p in items], "total": total, "perPage": per_page}
```

## File Uploads

```python
from quart import current_app
from werkzeug.utils import secure_filename

@bp.post("/api/product/<int:id>/image")
@auth_required("session")
@roles_required("admin")
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

## Vue Dialog Patterns

Complete CRUD with dialogs:

```javascript
createApp({
  delimiters: ['${', '}'],
  setup() {
    const items = ref([]);
    const total = ref(0);
    const loading = ref(false);
    const dialog = ref(false);
    const confirmDialog = ref(false);
    const editMode = ref(false);
    const saving = ref(false);
    const deleting = ref(false);
    const selectedItem = ref(null);
    const form = ref({ name: '', price: 0, category_id: null });
    const snackbar = ref({ show: false, text: '', color: '' });

    async function loadItems({ page, itemsPerPage }) {
      loading.value = true;
      const res = await axios.get('/api/products', { params: { page, per_page: itemsPerPage } });
      items.value = res.data.items;
      total.value = res.data.total;
      loading.value = false;
    }

    function openCreate() {
      editMode.value = false;
      form.value = { name: '', price: 0, category_id: null };
      dialog.value = true;
    }

    function editItem(item) {
      editMode.value = true;
      selectedItem.value = item;
      form.value = { ...item };
      dialog.value = true;
    }

    async function saveItem() {
      try {
        saving.value = true;
        const url = editMode.value
          ? `/api/product/${selectedItem.value.id}`
          : '/api/product/';
        await axios.post(url, form.value);
        dialog.value = false;
        loadItems({ page: 1, itemsPerPage: 25 });
      } catch (error) {
        snackbar.value = {
          show: true,
          text: error.response?.data?.message || 'Save failed',
          color: 'error',
        };
      } finally {
        saving.value = false;
      }
    }

    function deleteItem(item) {
      selectedItem.value = item;
      confirmDialog.value = true;
    }

    async function confirmDelete() {
      try {
        deleting.value = true;
        await axios.delete(`/api/product/${selectedItem.value.id}`);
        confirmDialog.value = false;
        loadItems({ page: 1, itemsPerPage: 25 });
      } catch (error) {
        snackbar.value = {
          show: true,
          text: error.response?.data?.message || 'Delete failed',
          color: 'error',
        };
      } finally {
        deleting.value = false;
      }
    }

    return {
      items, total, loading, dialog, confirmDialog, editMode,
      saving, deleting, form, snackbar,
      openCreate, editItem, saveItem, deleteItem, confirmDelete, loadItems,
    };
  }
}).use(createVuetify(vuetifyConfig)).mount('#app');
```

## Error Handling

API endpoints return `{"message": "..."}` on errors:

```python
@bp.post("/api/product/")
@auth_required("session")
@roles_required("admin")
async def create_product():
    data = await request.json
    if not data.get("name"):
        return {"message": "Name is required"}, 400
    product = await Product.from_dict(data)
    g.db_session.add(product)
    await g.db_session.commit()
    return {"item": product.to_dict()}
```

Global error handler in `app.py` catches unhandled exceptions, rolls back the session, and returns JSON for API requests or renders an error template otherwise.
