from datetime import datetime

import orjson as json
from quart import Blueprint, Response, g, request
from quart_security import auth_required, current_user
from sqlalchemy import func, select, update

from stk.notification.models import Notification

bp_notification = Blueprint("notifications", __name__)

PER_PAGE = 20


@bp_notification.before_request
@auth_required("session")
async def before_request():
    pass


@bp_notification.after_request
async def add_header(response):
    response.headers["Cache-Control"] = "private, no-store"
    return response


def own():
    return Notification.user_id == current_user.id


@bp_notification.get("/api/notifications")
async def list_notifications():
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(max(request.args.get("per_page", PER_PAGE, type=int), 1), 100)
    total = await g.db_session.scalar(select(func.count()).where(own()))
    result = await g.db_session.execute(
        select(Notification)
        .where(own())
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    items = [n.to_dict() for n in result.scalars().all()]
    return Response(
        json.dumps({"items": items, "total": total, "perPage": per_page}),
        content_type="application/json",
    )


@bp_notification.get("/api/notifications/unread")
async def unread_count():
    count = await g.db_session.scalar(
        select(func.count()).where(own(), Notification.read_at.is_(None))
    )
    return {"count": count}


@bp_notification.post("/api/notifications/<int:id>/read")
async def mark_read(id):
    notification = await g.db_session.scalar(
        select(Notification).where(own(), Notification.id == id)
    )
    if notification is None:
        return {"message": "Notification not found"}, 404
    notification.read_at = notification.read_at or datetime.now()
    await g.db_session.commit()
    return {"message": "Notification marked read"}


@bp_notification.post("/api/notifications/read")
async def mark_all_read():
    await g.db_session.execute(
        update(Notification)
        .where(own(), Notification.read_at.is_(None))
        .values(read_at=datetime.now())
    )
    await g.db_session.commit()
    return {"message": "All notifications marked read"}
