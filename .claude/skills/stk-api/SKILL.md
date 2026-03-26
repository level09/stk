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
!`grep -rn "@bp\.\(get\|post\|put\|delete\|patch\)" stk/*/views.py 2>/dev/null | head -30`

## Steps

1. **Find the model** named `$ARGUMENTS` in the codebase. Read its full definition to understand fields, relationships, and existing `to_dict()`/`from_dict()`.

2. **Generate these endpoints** in the model's blueprint views.py:

   - `GET /api/<plural>` - List with pagination, search, filtering
   - `POST /api/<singular>/` - Create
   - `POST /api/<singular>/<id>` - Update (POST, not PUT, matches stk convention)
   - `DELETE /api/<singular>/<id>` - Delete

3. **Every endpoint must:**
   - Be `async def`
   - Use `@auth_required("session")` (add `@roles_required("admin")` if admin-only)
   - Access DB via `await g.db_session.execute(...)` or `await g.db_session.get(...)`
   - Use `select()` and `.where()` from sqlalchemy (NOT `.filter()`)
   - Log mutations via `await Activity.register(current_user.id, "Action", data)`
   - Return dicts directly (NOT `jsonify()`)

4. **List endpoint must include:**
   - `page` and `per_page` query params
   - Optional `search` param with `ilike` on text fields
   - Total count via `select(func.count()).select_from(query.subquery())`
   - Response: `{"items": [...], "total": N, "perPage": N}`

5. **Error responses:** Return `{"message": "..."}` with appropriate status codes (400, 404).

6. **Verify:**
   - Run `uv run ruff check --fix . && uv run ruff format .`
   - Run `uv run python checks.py`
