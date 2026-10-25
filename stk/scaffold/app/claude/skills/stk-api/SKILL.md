---
name: stk-api
description: |
  Generate async CRUD API endpoints for an existing stk model. Use when adding API routes, REST endpoints, or CRUD operations to an stk blueprint.
argument-hint: "[ModelName]"
---

# Generate CRUD API for $ARGUMENTS

## Current state

Models available:
!`grep -rn "class.*Base" */*/models.py 2>/dev/null`

Existing API routes:
!`grep -rn "@bp_[a-z_]*\.\(get\|post\|put\|delete\|patch\|route\)" */*/views.py 2>/dev/null | head -30`

## Steps

1. **Find the model** named `$ARGUMENTS` in the codebase. Read its full definition to understand fields, relationships, and existing `to_dict()`/`from_dict()`.

2. **Generate these endpoints** in the model's blueprint views.py:

   - `GET /api/<plural>` — List with pagination, search, filtering
   - `POST /api/<singular>/` — Create (note trailing slash)
   - `POST /api/<singular>/<id>` — Update (POST, not PUT — stk convention)
   - `DELETE /api/<singular>/<id>` — Delete

3. **Follow the conventions** in https://docs.stk.dev/api/: blueprint-level auth, `{item: {...}}`
   payloads, `{items, total, perPage}` list responses via `orjson`, `Activity.register` on
   every mutation, rollback plus `log.exception` on failure, and `{"message": ...}` with
   400/404/412. The reference implementation is what `uv run stk new` writes
   (`render_views` in `stk/scaffold/templates.py`); match it.

4. **List endpoint:** `PER_PAGE = 25`, `page`/`per_page` params, an optional `search` param
   with `ilike` on the text fields, and the total counted from `query.subquery()` so filters
   apply to it.

5. **Create/Update:** create calls `await Model().from_dict(data)` and `flush()`es before the
   audit entry so the ID exists; update stores `to_dict()` before changing the row and logs
   old and new.

6. **If a page route doesn't exist yet**, add one:
   ```python
   @bp.get("/<plural>/")
   async def <plural>_page():
       return await render_template("<name>/index.html")
   ```

7. **Verify:**
   - Run `uv run ruff check --fix . && uv run ruff format .`
   - Run `uv run stk verify`
