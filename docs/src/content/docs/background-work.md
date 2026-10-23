---
title: "Background Work"
description: "Fire-and-forget tasks without Celery"
---

Use `run_in_background()` for fire-and-forget async tasks. There is no Celery and no Redis requirement; the task runs on the current event loop and exceptions are logged.

```python
from stk.tasks import run_in_background

async def send_email(user_id):
    ...

await run_in_background(send_email(user.id))
```

For tasks that need their own DB session, `run_with_session` opens one, commits on success, and rolls back on error:

```python
from stk.tasks import run_with_session

async def cleanup_old_records(session):
    await session.execute(...)

await run_with_session(cleanup_old_records)
```
