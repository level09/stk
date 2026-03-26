---
name: stk-blueprint
description: |
  Scaffold a new stk blueprint with models, views, templates, and Alembic migration. Use when creating a new feature module, adding a new section to the app, or scaffolding a blueprint.
argument-hint: "[blueprint-name]"
---

# Scaffold stk Blueprint

Create a complete blueprint for `$ARGUMENTS` in the stk framework.

## Current project state

Existing blueprints:
!`ls -d stk/*/views.py 2>/dev/null | sed 's|stk/||;s|/views.py||'`

Registered in app.py:
!`grep -E 'register_blueprint|from stk\.' stk/app.py`

## Steps

1. **Create the blueprint directory** at `stk/$ARGUMENTS/`:
   - `__init__.py` (empty)
   - `models.py` with at least one model inheriting from `Base` (NOT `db.Model`)
   - `views.py` with Blueprint, page route, and CRUD API endpoints

2. **Models must follow stk conventions:**
   - Import `Base` from `stk.extensions`, NOT `db`
   - Use `Column(Type)` from sqlalchemy directly
   - All relationships use `lazy="selectin"`
   - Include `to_dict()` and async `from_dict()` classmethod
   - Include `created_at = Column(DateTime, default=datetime.now, nullable=False)`

3. **Views must be async:**
   - ALL handlers are `async def`
   - DB access via `g.db_session` with `await`
   - Auth via `@auth_required("session")` from `quart_security`
   - Manual pagination: `offset().limit()` + `select(func.count())`
   - Log mutations: `await Activity.register(current_user.id, "Action", data)`
   - Return dicts, not jsonify

4. **Create template** at `stk/templates/$ARGUMENTS/index.html`:
   - Extend `layout.html`
   - Vue 3 + Vuetify with `delimiters: ['${', '}']`
   - Use `v-data-table-server` for lists
   - Fetch from API endpoints

5. **Register the blueprint** in `stk/app.py`:
   - Add import and `app.register_blueprint(bp)` following existing pattern

6. **Generate Alembic migration:**
   - Run: `uv run quart db revision -m "add $ARGUMENTS tables"`
   - Review the generated migration for correctness

7. **Verify:**
   - Run `uv run ruff check --fix . && uv run ruff format .`
   - Run `uv run python checks.py`

## Do NOT:
- Use `db.Model`, `db.Column`, `db.select()`, or any Flask-SQLAlchemy patterns
- Use `from flask import ...` or `from flask_security import ...`
- Use sync handlers (every route must be `async def`)
- Use `jsonify()` (return dicts directly)
- Use `lazy="dynamic"` on relationships (breaks async)
- Forget `await` on DB operations
