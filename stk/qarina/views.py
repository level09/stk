import asyncio
import logging
import os
import threading
from datetime import datetime

from quart import Blueprint, g, render_template, request, websocket
from quart_security import auth_required, current_user
from sqlalchemy import delete, select

import stk.extensions as ext
from stk.user.models import Activity

from .agent import run
from .models import ResearchRun

log = logging.getLogger("stk.qarina")
bp = Blueprint("qarina", __name__, url_prefix="/research")

_max_concurrent = max(int(os.environ.get("QUARINA_MAX_CONCURRENT_RUNS", "2")), 1)
_slots = threading.BoundedSemaphore(_max_concurrent)
_active_users: set[int] = set()
_active_users_lock = threading.Lock()


@bp.before_request
@auth_required("session")
async def require_auth():
    pass


@bp.get("/")
async def index():
    return await render_template("qarina/index.html")


@bp.get("/<int:run_id>")
async def session_page(run_id: int):
    result = await g.db_session.execute(
        select(ResearchRun.id).where(
            ResearchRun.id == run_id, ResearchRun.user_id == current_user.id
        )
    )
    if result.scalar_one_or_none() is None:
        return "Not found", 404
    return await render_template("qarina/index.html")


@bp.get("/api/history")
async def history_list():
    try:
        limit = min(max(int(request.args.get("limit", 50)), 1), 200)
        offset = max(int(request.args.get("offset", 0)), 0)
    except (TypeError, ValueError):
        limit, offset = 50, 0
    result = await g.db_session.execute(
        select(ResearchRun)
        .where(ResearchRun.user_id == current_user.id)
        .order_by(ResearchRun.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [run.summary() for run in result.scalars().all()]


@bp.get("/api/history/<int:run_id>")
async def history_get(run_id: int):
    run_record = await _get_owned_run(run_id)
    if not run_record:
        return {"error": "Not found"}, 404
    return run_record.to_dict()


@bp.delete("/api/history/<int:run_id>")
async def history_delete(run_id: int):
    result = await g.db_session.execute(
        delete(ResearchRun).where(
            ResearchRun.id == run_id, ResearchRun.user_id == current_user.id
        )
    )
    if result.rowcount != 1:
        return {"error": "Not found"}, 404
    await g.db_session.commit()
    return {"ok": True}


async def _get_owned_run(run_id: int) -> ResearchRun | None:
    result = await g.db_session.execute(
        select(ResearchRun).where(
            ResearchRun.id == run_id, ResearchRun.user_id == current_user.id
        )
    )
    return result.scalar_one_or_none()


async def _update_run(
    run_id: int,
    user_id: int,
    *,
    status: str,
    report: str | None = None,
    error: str | None = None,
):
    async with ext.async_session_factory() as session:
        result = await session.execute(
            select(ResearchRun).where(
                ResearchRun.id == run_id, ResearchRun.user_id == user_id
            )
        )
        run_record = result.scalar_one_or_none()
        if not run_record:
            return
        run_record.status = status
        run_record.report = report
        run_record.error = error
        run_record.completed_at = datetime.now()
        session.add(
            Activity(
                user_id=user_id,
                action=f"research_run_{status}",
                data={"run_id": run_id, "query": run_record.query[:200]},
            )
        )
        await session.commit()


@bp.websocket("/ws")
async def research_ws():
    if not current_user.is_authenticated:
        await websocket.close(4001, "Unauthorized")
        return

    data = await websocket.receive_json()
    query = (data.get("query") or "").strip()
    if not query:
        await websocket.send_json({"type": "error", "message": "Empty query"})
        await websocket.close()
        return

    with _active_users_lock:
        if current_user.id in _active_users:
            await websocket.send_json(
                {"type": "error", "message": "You already have a research run active"}
            )
            await websocket.close()
            return
        _active_users.add(current_user.id)

    if not _slots.acquire(blocking=False):
        with _active_users_lock:
            _active_users.discard(current_user.id)
        await websocket.send_json(
            {"type": "error", "message": "Research capacity is currently full"}
        )
        await websocket.close()
        return

    user_id = current_user.id
    config = dict(data.get("config") or {})
    config["knowledge_namespace"] = user_id
    run_record = ResearchRun(
        user_id=user_id,
        query=query,
        sources=config.get("sources", {}),
        status="running",
    )
    g.db_session.add(run_record)
    await g.db_session.commit()
    run_id = run_record.id
    db_session = g.pop("db_session", None)
    if db_session is not None:
        await db_session.close()

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    stop = threading.Event()
    report = None
    run_status = "completed"

    def put(event):
        try:
            loop.call_soon_threadsafe(queue.put_nowait, event)
        except RuntimeError:
            pass

    def worker():
        generator = run(query, config=config)
        try:
            for event in generator:
                put(event)
                if stop.is_set():
                    put({"type": "stopped"})
                    break
        except Exception as exc:
            log.exception("Qarina run failed")
            put({"type": "error", "message": str(exc)})
        finally:
            generator.close()
            put(None)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    async def reader():
        try:
            while True:
                message = await websocket.receive_json()
                if message.get("type") == "stop":
                    stop.set()
        except Exception:
            stop.set()

    reader_task = asyncio.create_task(reader())
    try:
        while True:
            event = await queue.get()
            if event is None:
                break
            if event.get("type") == "start":
                await _set_run_model(run_id, event.get("model"))
            elif event.get("type") == "report":
                report = event.get("content", "")
            elif event.get("type") == "error":
                run_status = "failed"
            elif event.get("type") == "stopped":
                run_status = "cancelled"
            await websocket.send_json(event)
        await _update_run(run_id, user_id, status=run_status, report=report, error=None)
        await websocket.send_json({"type": "saved", "session_id": run_id})
    except Exception:
        stop.set()
        run_status = "cancelled"
        await _update_run(run_id, user_id, status=run_status, report=report)
    finally:
        stop.set()
        reader_task.cancel()
        _slots.release()
        with _active_users_lock:
            _active_users.discard(user_id)
        try:
            await websocket.close()
        except Exception:
            pass


async def _set_run_model(run_id: int, model: str | None):
    if not model:
        return
    async with ext.async_session_factory() as session:
        result = await session.execute(
            select(ResearchRun).where(ResearchRun.id == run_id)
        )
        run_record = result.scalar_one_or_none()
        if run_record:
            run_record.model = model
            await session.commit()
