---
title: "JSON APIs"
description: "List and mutation endpoints, error conventions, CSRF, webhooks, fetching user-supplied URLs, and file uploads"
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

## File uploads

`stk.files` is opt-in: add it to the app's extensions, `Stk(__name__, config=Config, extensions=[stk.files, ...])` with `import stk.files`. Its table, `stk_file`, comes with `uv run stk db upgrade` either way.

| Route | Does |
|---|---|
| `POST /files/` | Multipart upload of one field named `file`, login required. Returns `{"item": {id, filename, size, content_type, sha256, url, thumb_url, user_id, created_at}}`. |
| `GET /files/<id>` | The bytes, if `app.file_access` allows. |
| `GET /files/<id>/thumb` | A WebP no larger than 480px on its long side, for images. |

```js
const form = new FormData();
form.append("file", file);
const { data } = await axios.post("/files/", form);
```

The content type comes from the file's leading bytes, never from the client: PNG, JPEG, GIF, WebP, and PDF are recognized, anything else is refused with 415, and a file over `STK_UPLOAD_MAX_BYTES` with 413. Send the CSRF token in the `X-CSRFToken` header (Axios does); a token inside the form makes the body parse under Quart's `MAX_CONTENT_LENGTH` instead of the upload limit. An image is decoded once at upload to make its thumbnail, so bytes that only look like an image are refused with 400. The same user uploading the same bytes again gets the existing row back.

Downloads send `X-Content-Type-Options: nosniff`, a sandboxing `Content-Security-Policy`, and `Cache-Control: private, no-store`. Images display inline; every other type downloads as an attachment under its original name. A file the user may not read answers 404, so ids reveal nothing.

By default only the uploader and admins may read a file. Replace the check after building the app with an async function of the user and the `File` row:

```python
from stk.files.views import can_read


async def file_access(user, file):
    return await can_read(user, file) or await is_shared_with(user, file)


app.file_access = file_access
```

Bytes are content-addressed on local disk at `<STK_UPLOAD_DIR>/<sha[:2]>/<sha>`, written to a temp file and renamed, so equal bytes are stored once and a crash never leaves half a file. `stk.files.store` gives tasks and commands the same store: `save(data)` returns the sha256, `open(sha)`, `path(sha)`, `exists(sha)`, `delete(sha)`. Keys must be 64 lowercase hex characters, so no key reaches outside the directory. Rows share bytes, so delete bytes only once no `File` names them. In Docker, point `STK_UPLOAD_DIR` at a mounted volume; the default under `instance/` does not survive a rebuilt container. One machine's disk is the ceiling: move to object storage when a second app server needs the files.
