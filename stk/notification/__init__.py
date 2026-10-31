"""Stored, per-user notifications. The row is the truth; the socket push is a nudge."""

import stk.extensions as ext
from stk.notification.models import Notification
from stk.websocket import broadcast


async def notify(user_id, title, link=None, kind=None, body=None):
    """Store a notification for one user, commit it, then push it to their sockets.

    Commits on its own session, so a caller's rollback does not undo it: call it
    after your own commit. `link` must be a same-origin path such as `/exports/3`.
    """
    # The bell navigates to `link`; a `javascript:` or off-site URL would run there.
    if link is not None and (
        not link.startswith("/") or link.startswith(("//", "/\\"))
    ):
        raise ValueError(f"link must be a same-origin path, got {link!r}")
    async with ext.async_session_factory() as db:
        row = Notification(
            user_id=user_id, title=title, link=link, kind=kind, body=body
        )
        db.add(row)
        await db.commit()
    await broadcast({"type": "notification", **row.to_dict()}, user_id)
    return row
