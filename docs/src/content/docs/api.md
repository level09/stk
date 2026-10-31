---
title: "JSON APIs"
description: "List and mutation endpoints, error conventions, CSRF, webhooks, and MCP tools for agents"
---

`uv run stk new <module>` writes a complete, working set of these endpoints in `myapp/<module>/views.py`. Start from that file; this page explains its conventions.

## List endpoints

Lists paginate manually and serialize with `orjson`. The response shape is `{items, total, perPage}`, which is what the frontend's [server-paginated table](/frontend#server-paginated-table) expects.

```python
import orjson as json
from quart import Response, g, request
from sqlalchemy import func, or_, select

PER_PAGE = 25


@bp.get("/api/posts")
async def list_posts():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE, type=int)

    query = select(Post)
    if search := request.args.get("search"):
        query = query.where(
            or_(Post.title.ilike(f"%{search}%"), Post.content.ilike(f"%{search}%"))
        )

    total = await g.db_session.scalar(
        select(func.count()).select_from(query.subquery())
    )
    result = await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )
    items = [p.to_dict() for p in result.scalars().all()]
    return Response(
        json.dumps({"items": items, "total": total, "perPage": per_page}),
        content_type="application/json",
    )
```

Count from `query.subquery()` so filters apply to the total too.

## Mutations

The frontend sends `{item: {...}}`. Create is `POST /api/post/`, update is `POST /api/post/<id>` (POST, not PUT), delete is `DELETE /api/post/<id>`. Admin mutations are logged with `Activity.register`.

```python
@bp.post("/api/post/")
async def create_post():
    data = (await request.json).get("item", {})
    if not data.get("title"):
        return {"message": "Title is required"}, 400
    post = await Post().from_dict(data)
    g.db_session.add(post)
    try:
        await g.db_session.flush()  # assigns post.id for the audit entry
        await Activity.register(current_user.id, "Post Create", post.to_dict())
        await g.db_session.commit()
        return {"message": "Post created"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error creating post")
        return {"message": "Error creating post"}, 412
```

Responses are `{"message": ...}`: 400 for invalid input, 404 for a missing row, 412 for a failed write. An unhandled exception reaches stk's global error handler (`stk/app.py`), which rolls back the session and returns JSON for API requests.

## Protecting endpoints

Put auth on the blueprint so no route can forget it:

```python
@bp.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass
```

`uv run stk inspect routes --json` reports which routes are guarded, and `stk verify` fails if a route reported as guarded is reachable anonymously.

## CSRF and webhooks

Every mutation requires a CSRF token, which Axios sends from the shared layout token. A third-party webhook without a session opts out with `@csrf_exempt` from `stk.security`, placed under the route decorator, and must authenticate the caller itself, for example by checking an HMAC signature. See [Authentication](/authentication).

## Agent tools (MCP)

An app can expose its own functions to AI agents. stk serves them at `POST /mcp` as a stateless MCP server: MCP `2026-07-28` with `server/discover`, plus `initialize` and `ping` for clients on `2025-11-25`, `2025-06-18`, and `2025-03-26`. Every reply is one JSON object; there are no sessions and no SSE.

Register a tool with `@tool` from `stk.mcp`, in any module your extension imports:

```python
from quart import g
from quart_security import current_user
from sqlalchemy import select
from stk.mcp import ToolError, tool


@tool(
    "notes.search",
    "Search the caller's notes by title.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}},
        "required": ["query"],
        "additionalProperties": False,
    },
    role="editor",
)
async def search_notes(arguments):
    rows = await g.db_session.scalars(
        select(Note).where(
            Note.user_id == current_user.id,
            Note.title.ilike(f"%{arguments['query']}%"),
        )
    )
    notes = [n.to_dict() for n in rows]
    if not notes:
        raise ToolError("No notes match; try a shorter query")
    return {"notes": notes}
```

The tool receives arguments already validated against its JSON Schema, and runs as the token's user: `current_user` and `g.db_session` work as in a handler, so apply the same ownership checks a route would. A returned object becomes `structuredContent`; raise `ToolError` for a message the agent can act on. stk commits after the tool returns and rolls back on any error, then logs one `MCP Tool Call` activity naming the tool and token, never the arguments.

Each user creates and revokes tokens at `/tokens/` (Account → Agent Tokens). A token is shown once, stored only as its sha256, and expires after 90 days. Its scopes are roles the user holds; a tool with `role="editor"` needs a token scoped to `editor` and a user who still holds that role, checked on every call. A tool without a role is open to any valid token. `tools/list` shows each token only the tools it can call.

An agent sends the token as `Authorization: Bearer <token>`. For Claude Code:

```bash
claude mcp add --transport http myapp https://myapp.example.com/mcp --header "Authorization: Bearer stk_mcp_..."
```

The endpoint is exempt from CSRF because a session cookie never authenticates it, refuses a foreign `Origin`, and allows 120 requests per token per minute (`STK_MCP_REQUEST_LIMIT`). There is no OAuth authorization server yet, so clients that only support MCP's OAuth discovery cannot connect; give them a header instead.
