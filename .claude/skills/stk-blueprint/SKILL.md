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

Navigation items:
!`grep -E 'title:|heading:' stk/static/js/navigation.js 2>/dev/null | head -20`

## Steps

1. **Create the blueprint directory** at `stk/$ARGUMENTS/`:
   - `__init__.py` (empty)
   - `models.py` with model(s) inheriting from `Base`
   - `views.py` with Blueprint, page route, and CRUD API endpoints

2. **Models must follow stk conventions:**
   - `import dataclasses` and use `@dataclasses.dataclass` decorator
   - Import `Base` from `stk.extensions`, NOT `db`
   - Use `Column(Type)` from sqlalchemy directly
   - All relationships use `lazy="selectin"`
   - Include `to_dict()` instance method
   - Include `async from_dict(self, data)` as **instance method** that mutates self (NOT a classmethod)
   - Include `created_at = Column(DateTime, default=datetime.now, nullable=False)`

3. **Views must follow the real codebase patterns:**
   - ALL handlers are `async def`
   - Use `import orjson as json` and return `Response(json.dumps(data), content_type="application/json")` for list endpoints
   - Blueprint-level auth via `@bp.before_request` with `@auth_required("session")` (add `@roles_required("admin")` if admin-only)
   - DB access via `await g.db_session.execute(...)` or `await g.db_session.get(...)`
   - Frontend sends `{item: {...}}`, extract with `json_data.get("item", {})`
   - Wrap mutations in try/except with `await g.db_session.rollback()` on error
   - Log mutations: `await Activity.register(current_user.id, "Action", data)`
   - Return `{"message": "..."}` for create/update/delete responses
   - Use `PER_PAGE = 25` constant
   - Use `log = logging.getLogger(__name__)` for error logging

4. **Create template** at `stk/templates/$ARGUMENTS/index.html` or `stk/templates/cms/$ARGUMENTS.html`:
   - Extend `layout.html`
   - Vue 3 Options API: `data()`, `methods`, `mounted()`, NOT `setup()`
   - Must include `mixins: [layoutMixin]` and `delimiters: config.delimiters`
   - Use `const vuetify = createVuetify(config.vuetifyConfig)`
   - Call `registerStkComponents(app)` before `app.use(vuetify).mount("#app")`
   - Use `v-data-table-server` for lists
   - Icons: Tabler Icons (`ti ti-*`), e.g. `ti ti-plus`, `ti ti-pencil`, `ti ti-trash`, `ti ti-x`
   - Pass server data via `<script type="application/json" id="...">{{ data|tojson|safe }}</script>`
   - Use `toRaw()` from Vue when editing items: `const {createApp, toRaw} = Vue`

5. **Register the blueprint** in `stk/app.py`:
   - Add import at top with other blueprint imports
   - Add `app.register_blueprint(bp)` in `register_blueprints()`

6. **Add navigation entry** in `stk/static/js/navigation.js`:
   ```javascript
   // Simple link (role is singular string, not array)
   { title: '$ARGUMENTS', icon: 'ti ti-<icon>', to: '/$ARGUMENTS', role: 'admin' },

   // Or grouped with children
   {
     title: '$ARGUMENTS', icon: 'ti ti-<icon>', role: 'admin',
     children: [
       { title: 'List', icon: 'ti ti-list', to: '/$ARGUMENTS' },
     ]
   },
   ```

7. **Generate Alembic migration:**
   - Run: `uv run quart db revision -m "add $ARGUMENTS tables"`
   - Review the generated migration for correctness

8. **Verify:**
   - Run `uv run ruff check --fix . && uv run ruff format .`
   - Run `uv run python checks.py`

## Do NOT:
- Use `db.Model`, `db.Column`, `db.select()`, or any Flask-SQLAlchemy patterns
- Use `from flask import ...` or `from flask_security import ...`
- Use sync handlers (every route must be `async def`)
- Use `jsonify()` (return dicts or Response objects)
- Use `lazy="dynamic"` on relationships (breaks async)
- Forget `await` on DB operations
- Use Vue Composition API (`setup()`, `ref()`, `reactive()`) — use Options API
- Use Material Design Icons — use Tabler Icons (`ti ti-*`)
- Send raw data in POST — wrap in `{item: {...}}`
- Forget `mixins: [layoutMixin]` or `registerStkComponents(app)` in templates
