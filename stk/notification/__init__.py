"""Stored, per-user notifications. The row is the truth; the socket push is a nudge.

Opt in with `extensions=[stk.notification, ...]` for the `/api/notifications`
routes and the layout's bell; `notify()` stores rows either way.
"""

import stk.extensions as ext
from stk.notification.models import Notification
from stk.websocket import broadcast


async def notify(user_id, title, link=None, kind=None, body=None, session=None):
    """Store a notification for one user and push it to their sockets.

    With `session`, both join that transaction: they land at commit and vanish on
    rollback. Without it, they commit on their own session.
    `link` must be a same-origin path such as `/exports/3`.
    """
    # The bell navigates to `link`; a `javascript:` or off-site URL would run there.
    # Browsers strip tabs and newlines from URLs, so "/\t/evil" becomes "//evil".
    if link is not None and (
        not link.startswith("/")
        or link.startswith(("//", "/\\"))
        or any(c.isspace() or ord(c) < 0x20 or ord(c) == 0x7F for c in link)
    ):
        raise ValueError(f"link must be a same-origin path, got {link!r}")
    row = Notification(user_id=user_id, title=title, link=link, kind=kind, body=body)
    if session is not None:
        await _store(session, row)
        return row
    async with ext.async_session_factory() as db:
        await _store(db, row)
        await db.commit()
    return row


async def _store(db, row):
    db.add(row)
    await db.flush()  # id and created_at for the pushed copy
    await broadcast({"type": "notification", **row.to_dict()}, row.user_id, db)


def init_app(app):
    from stk.notification.views import bp_notification

    app.extensions["stk.notification"] = True
    app.jinja_env.globals["stk_notifications"] = True
    app.register_blueprint(bp_notification)
