---
title: "JSON APIs"
description: "List and mutation endpoints, error conventions, CSRF, webhooks, and fetching user-supplied URLs"
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

## Fetching user-supplied URLs

Never pass a URL a user or client typed to `httpx2` directly: it can point at `localhost`, the database host, or the cloud metadata service at `169.254.169.254`. Use `fetch` from `stk.utils.netguard`:

```python
import httpx2

from stk.utils.netguard import Blocked, fetch


@bp.post("/api/preview")
async def preview():
    url = (await request.json).get("item", {}).get("url", "")
    try:
        response, final_url = await fetch(url, timeout=5, max_bytes=500_000)
    except Blocked as exc:
        return {"message": str(exc)}, 400
    except (TimeoutError, httpx2.HTTPError):
        return {"message": "URL could not be fetched"}, 412
    return {"status": response.status_code, "url": final_url}
```

`fetch` sends a GET and returns the response with its body read, plus the URL after redirects. It resolves the host once, refuses it unless every address is public, and connects to that exact address while TLS still verifies the hostname, so DNS rebinding cannot swap in an internal address after the check. Every redirect hop is checked the same way, and `Authorization` and `Cookie` headers are dropped once a redirect leaves the original host.

It raises `Blocked` for anything other than `http` or `https`, credentials in the URL, decimal, octal or hex IP literals (`2130706433`, `0x7f.1`), loopback, private, link-local, CGNAT, multicast, reserved and unspecified addresses (IPv4 and IPv6, including IPv4-mapped and NAT64 forms), more than `max_redirects` redirects (default 5), and a body over `max_bytes` after decompression (default 1 MiB). `timeout` (default 10 seconds) bounds the whole fetch and raises `TimeoutError`. Environment proxies are ignored, since a proxy would resolve the name itself. In tests, pass `transport=httpx2.MockTransport(handler)`.
