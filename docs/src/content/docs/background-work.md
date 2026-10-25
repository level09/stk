---
title: "Background Work"
description: "Fire-and-forget tasks without Celery, and pushing messages over WebSockets"
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

## WebSockets

Signed-in pages connect to `/ws` automatically through `layoutMixin`. Push a message to one user with `broadcast`:

```python
from stk.websocket import broadcast

await broadcast(
    {"type": "notification", "title": "Export ready", "to": "/exports"}, user_id=user.id
)
```

There is no broadcast-to-everyone: every message names its recipient. `{type: 'notification'}` messages land in the notification bell; extend `_onWsMessage` in `layout.html` for your own types. `Activity.register()` stores audit events and does not broadcast.

The endpoint enforces:

- an `Origin` matching `STK_PUBLIC_URL` (or the request host), overridable with `STK_WS_ALLOWED_ORIGINS`
- a signed-in session, rechecked every `STK_WS_AUTH_INTERVAL` seconds (5), so logout or deactivation closes the socket
- at most `STK_WS_CONNECTIONS_PER_USER` (5) and `STK_WS_MAX_CONNECTIONS` (1000) connections
- at most `STK_WS_MESSAGE_LIMIT` (60) client messages per minute, each up to `STK_WS_MESSAGE_SIZE` (65536) bytes
- a send queue of `STK_WS_QUEUE_SIZE` (32); a client that falls behind is disconnected

These are app config values: set them on your `Config` class, not in `.env`.

Connected clients are tracked in process memory, so `broadcast` reaches only sockets held by the same worker. With several uvicorn workers, a message sent from one worker misses users connected to another. Run one worker, or fan out through Redis pub/sub if you need more.
