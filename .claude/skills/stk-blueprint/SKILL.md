---
name: stk-blueprint
description: |
  Scaffold a new stk blueprint with models, views, templates, and Alembic migration. Use when creating a new feature module, adding a new section to the app, or scaffolding a blueprint.
argument-hint: "[blueprint-name]"
---

# Scaffold stk Blueprint

Create a complete blueprint for `$ARGUMENTS` in the stk framework.

## Workflow

The scaffolder generates the full module structure. Run it first, then customize domain fields and logic.

```bash
uv run quart new <name>
```

`<name>` must be lowercase snake_case (e.g. `blog_post`, `invoice_line`). Reserved names (`user`, `role`, `portal`, `public`, `session`, `admin`, etc.) are rejected with a clear error.

The command generates:
- `stk/<name>/__init__.py`, `models.py`, `views.py`
- `stk/templates/cms/<name>.html`
- Patches `stk/app.py` (import + `register_blueprint`)
- Patches `stk/static/js/navigation.js` (nav entry)

Then:
1. Customize `stk/<name>/models.py` -- add/rename fields to fit your domain
2. Run: `uv run quart db revision -m "add <name>"` and review the generated migration
3. Apply: `uv run quart db upgrade`
4. Verify: `uv run quart verify && uv run quart smoke`

## Customization reference

After scaffolding, the generated files follow these conventions. Only touch these when you need to go beyond the defaults.

### Models (`stk/<name>/models.py`)

- `import dataclasses` and use `@dataclasses.dataclass` decorator
- Import `Base` from `stk.extensions`, NOT `db`
- Use `Column(Type)` from sqlalchemy directly
- All relationships use `lazy="selectin"`
- Include `to_dict()` instance method
- Include `async from_dict(self, data)` as **instance method** that mutates self (NOT a classmethod)
- Include `created_at = Column(DateTime, default=datetime.now, nullable=False)`

### Views (`stk/<name>/views.py`)

- ALL handlers are `async def`
- Use `import orjson as json` and return `Response(json.dumps(data), content_type="application/json")` for list endpoints
- Blueprint-level auth via `@bp.before_request` with `@auth_required("session")` + `@roles_required("admin")`
- DB access via `await g.db_session.execute(...)` or `await g.db_session.get(...)`
- Frontend sends `{item: {...}}`, extract with `json_data.get("item", {})`
- Wrap mutations in try/except with `await g.db_session.rollback()` on error
- Log mutations: `await Activity.register(current_user.id, "Action", data)`
- Return `{"message": "..."}` for create/update/delete responses
- Use `PER_PAGE = 25` constant
- Use `log = logging.getLogger(__name__)` for error logging

### Template (`stk/templates/cms/<name>.html`)

- Extend `layout.html`
- Vue 3 Options API: `data()`, `methods`, `mounted()`, NOT `setup()`
- Must include `mixins: [layoutMixin]` and `delimiters: config.delimiters`
- Use `const vuetify = createVuetify(config.vuetifyConfig)`
- Call `registerStkComponents(app)` before `app.use(vuetify).mount("#app")`
- Use `v-data-table-server` for lists
- Icons: Tabler Icons (`ti ti-*`), e.g. `ti ti-plus`, `ti ti-pencil`, `ti ti-trash`, `ti ti-x`
- Pass server data via `<script type="application/json" id="...">{{ data|tojson|safe }}</script>`
- Use `toRaw()` from Vue when editing items: `const {createApp, toRaw} = Vue`

## Do NOT:
- Use `db.Model`, `db.Column`, `db.select()`, or any Flask-SQLAlchemy patterns
- Use `from flask import ...` or `from flask_security import ...`
- Use sync handlers (every route must be `async def`)
- Use `jsonify()` (return dicts or Response objects)
- Use `lazy="dynamic"` on relationships (breaks async)
- Forget `await` on DB operations
- Use Vue Composition API (`setup()`, `ref()`, `reactive()`) -- use Options API
- Use Material Design Icons -- use Tabler Icons (`ti ti-*`)
- Send raw data in POST -- wrap in `{item: {...}}`
- Forget `mixins: [layoutMixin]` or `registerStkComponents(app)` in templates
