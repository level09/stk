---
title: "Background Work"
description: "Fire-and-forget tasks without Celery, in-app notifications, and pushing messages over WebSockets"
---

## Background tasks

Use `run_in_background()` for fire-and-forget async tasks. There is no Celery and no Redis requirement; the task runs on the current event loop and exceptions are logged.

```python
from stk.tasks import run_in_background


async def send_email(user_id): ...


await run_in_background(send_email(user.id))
```

For tasks that need their own DB session, `run_with_session` opens one, commits on success, and rolls back on error:

```python
from stk.tasks import run_with_session


async def cleanup_old_records(session):
    await session.execute(...)


await run_with_session(cleanup_old_records)
```

Tasks live only as long as the process. Work that must survive a restart belongs in a table that a scheduled job drains, not in `run_in_background`.

`uv run stk cleanup-sessions` deactivates expired sessions and deletes rows older than 30 days. Run it from cron or a systemd timer.

## Notifications

`notify` stores a notification for one user in `stk_notification`, then pushes it to that user's open sockets, where it lands in the bell in the app bar:

```python
from stk.notification import notify

await notify(user.id, "Export ready", link="/exports/3", kind="export", body="March invoices")
```

Only `user_id` and `title` are required. `link` must be a same-origin path (`/exports/3`); anything else raises `ValueError`, because the bell navigates to it. `kind` is a free label for your own filtering. `notify` commits on its own session, so a later rollback in the caller does not undo it: call it after your own commit. It works the same from a request, a background task, or `stk shell`, though only a call inside the server process reaches open sockets; the others show up on the next page load.

The signed-in user reads and clears their own notifications; no endpoint returns another user's:

| Endpoint | Returns |
|---|---|
| `GET /api/notifications?page=&per_page=` | `{items, total, perPage}`, newest first, 20 per page, at most 100 |
| `GET /api/notifications/unread` | `{count}` |
| `POST /api/notifications/<id>/read` | marks one read; 404 if it is not yours |
| `POST /api/notifications/read` | marks all read |

Items are `{id, kind, title, body, link, created_at, read_at}`. The POSTs need CSRF and a JSON object body (`{}`), like every `/api/` mutation.

## WebSockets

Signed-in pages connect to `/ws` automatically through `layoutMixin`. Push a message that is not stored to one user with `broadcast`:

```python
from stk.websocket import broadcast

await broadcast({"type": "progress", "done": 40}, user_id=user.id)
```

There is no broadcast-to-everyone: every message names its recipient. `{type: 'notification'}` messages go to the bell; override `_onWsMessage(msg)` in your page's methods for your own types. `Activity.register()` stores audit events and does not broadcast.

The endpoint enforces:

- an `Origin` matching `STK_PUBLIC_URL` (or the request host), overridable with `STK_WS_ALLOWED_ORIGINS`
- a signed-in session, rechecked every `STK_WS_AUTH_INTERVAL` seconds (5), so logout or deactivation closes the socket
- at most `STK_WS_CONNECTIONS_PER_USER` (5) and `STK_WS_MAX_CONNECTIONS` (1000) connections
- at most `STK_WS_MESSAGE_LIMIT` (60) client messages per minute, each up to `STK_WS_MESSAGE_SIZE` (65536) bytes
- a send queue of `STK_WS_QUEUE_SIZE` (32); a client that falls behind is disconnected

These are app config values: set them on your `Config` class, not in `.env`.

Connected clients are tracked in process memory, so `broadcast` reaches only sockets held by the same worker. With several uvicorn workers, a message sent from one worker misses users connected to another. Run one worker, or fan out through Redis pub/sub if you need more.
