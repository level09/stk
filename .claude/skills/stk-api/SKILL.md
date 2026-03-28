---
name: stk-api
description: |
  Generate async CRUD API endpoints for an existing stk model. Use when adding API routes, REST endpoints, or CRUD operations to an stk blueprint.
argument-hint: "[ModelName]"
---

# Generate CRUD API for $ARGUMENTS

## Current state

Models available:
!`grep -rn "class.*Base" stk/*/models.py 2>/dev/null`

Existing API routes:
!`grep -rn "@bp\.\(get\|post\|put\|delete\|patch\)\|@bp\.route" stk/*/views.py 2>/dev/null | head -30`

## Steps

1. **Find the model** named `$ARGUMENTS` in the codebase. Read its full definition to understand fields, relationships, and existing `to_dict()`/`from_dict()`.

2. **Generate these endpoints** in the model's blueprint views.py:

   - `GET /api/<plural>` — List with pagination, search, filtering
   - `POST /api/<singular>/` — Create (note trailing slash)
   - `POST /api/<singular>/<id>` — Update (POST, not PUT — stk convention)
   - `DELETE /api/<singular>/<id>` — Delete

3. **Every endpoint must:**
   - Be `async def`
   - Use blueprint-level auth OR per-route `@auth_required("session")` + `@roles_required("admin")`
   - Access DB via `await g.db_session.execute(...)` or `await g.db_session.get(...)`
   - Use `select()` and `.where()` from sqlalchemy (NOT `.filter()` for new code, though existing code may use it)
   - Log mutations via `await Activity.register(current_user.id, "Action", data)`
   - Wrap mutations in try/except with `await g.db_session.rollback()` on error, `log.exception()` for logging
   - Return `{"message": "..."}` for success/error responses

4. **List endpoint must include:**
   - `PER_PAGE = 25` constant at module level
   - `page` and `per_page` query params
   - Optional `search` param with `ilike` on text fields
   - Total count via `await g.db_session.execute(select(func.count()).select_from(Model))` then `.scalar()`
   - Use `import orjson as json` and return `Response(json.dumps(response_data), content_type="application/json")`
   - Response shape: `{"items": [...], "total": N, "perPage": N}`

5. **Create/Update endpoints must:**
   - Extract data from `{item: {...}}` wrapper: `json_data.get("item", {})`
   - For create: instantiate model, call `await instance.from_dict(data)`, add to session
   - For update: get existing, store old data, call `await instance.from_dict(data)`
   - Use `await g.db_session.flush()` before activity logging on create (to get the ID)
   - Return 412 on error (matching existing convention)

6. **Error responses:** Return `{"message": "..."}` with status codes: 400 (validation), 404 (not found), 412 (server error).

7. **If a page route doesn't exist yet**, add one:
   ```python
   @bp.get("/<plural>/")
   async def <plural>_page():
       return await render_template("cms/<plural>.html")
   ```

8. **Verify:**
   - Run `uv run ruff check --fix . && uv run ruff format .`
   - Run `uv run python checks.py`
