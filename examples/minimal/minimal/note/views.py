"""Views for note blueprint."""

import logging

import orjson as json
from quart import Blueprint, Response, g, render_template, request
from quart_security import auth_required, current_user, roles_required
from sqlalchemy import func, select
from stk.user.models import Activity

from minimal.note.models import Note

log = logging.getLogger(__name__)

bp_note = Blueprint("note", __name__)

PER_PAGE = 25


@bp_note.before_request
@auth_required("session")
@roles_required("admin")
async def before_request():
    pass


@bp_note.get("/notes/")
async def notes_page():
    return await render_template("note/index.html")


@bp_note.get("/api/notes")
async def api_notes_list():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", PER_PAGE, type=int)
    search = request.args.get("search", "").strip()

    query = select(Note)
    count_query = select(func.count()).select_from(Note)

    if search:
        query = query.where(Note.name.ilike(f"%{search}%"))
        count_query = count_query.where(Note.name.ilike(f"%{search}%"))

    total = (await g.db_session.execute(count_query)).scalar()
    result = await g.db_session.execute(
        query.offset((page - 1) * per_page).limit(per_page)
    )
    items = [item.to_dict() for item in result.scalars().all()]

    return Response(
        json.dumps({"items": items, "total": total, "perPage": per_page}),
        content_type="application/json",
    )


@bp_note.post("/api/note/")
async def api_note_create():
    json_data = await request.json
    item_data = json_data.get("item", {})
    item = Note(user_id=current_user.id)
    await item.from_dict(item_data)
    g.db_session.add(item)
    try:
        await g.db_session.flush()
        await Activity.register(current_user.id, "Note Create", item.to_dict())
        await g.db_session.commit()
        return {"message": "Note successfully created!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error creating note")
        return {"message": "Error creating note"}, 412


@bp_note.post("/api/note/<int:id>")
async def api_note_update(id):
    item = await g.db_session.get(Note, id)
    if item is None:
        return {"message": "Note not found"}, 404
    json_data = await request.json
    item_data = json_data.get("item", {})
    old_data = item.to_dict()
    try:
        await item.from_dict(item_data)
        await g.db_session.flush()
        await Activity.register(
            current_user.id,
            "Note Update",
            {"old": old_data, "new": item.to_dict()},
        )
        await g.db_session.commit()
        return {"message": "Note successfully updated!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error updating note")
        return {"message": "Error updating note"}, 412


@bp_note.route("/api/note/<int:id>", methods=["DELETE"])
async def api_note_delete(id):
    item = await g.db_session.get(Note, id)
    if item is None:
        return {"message": "Note not found"}, 404
    old_data = item.to_dict()
    try:
        await g.db_session.delete(item)
        await Activity.register(current_user.id, "Note Delete", old_data)
        await g.db_session.commit()
        return {"message": "Note successfully deleted!"}
    except Exception:
        await g.db_session.rollback()
        log.exception("Error deleting note")
        return {"message": "Error deleting note"}, 412
