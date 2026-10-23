---
title: "JSON APIs"
description: "List and mutation endpoints, CSRF, and webhooks"
---

List endpoints paginate manually and serialize with `orjson`. Mutations arrive as `{item: {...}}` from the frontend.

```python
import orjson as json
from quart import Response, g, request
from sqlalchemy import func, select

@bp.route("/api/posts")
async def api_posts():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 25, type=int)
    total = (await g.db_session.execute(select(func.count()).select_from(Post))).scalar()
    result = await g.db_session.execute(
        select(Post).offset((page - 1) * per_page).limit(per_page)
    )
    items = [p.to_dict() for p in result.scalars().all()]
    data = {"items": items, "total": total, "perPage": per_page}
    return Response(json.dumps(data), content_type="application/json")

@bp.post("/api/post/")
async def api_post_create():
    json_data = await request.json
    item = json_data.get("item", {})
    ...
```

## CSRF and webhooks

Every mutation requires a CSRF token, which Axios sends from the shared layout token. A third-party webhook without a session opts out with `@csrf_exempt` from `stk.security`, placed under the route decorator, and must authenticate the caller itself. See [Authentication](/authentication).
