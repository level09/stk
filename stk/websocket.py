"""Bounded, same-origin WebSockets with periodic session validation.

Messages travel through the `stk_message` table, so `broadcast` reaches a user's
sockets from any process: another uvicorn worker, `stk worker`, or `stk shell`.
Each server process polls the table while it holds sockets.
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta

from quart import Blueprint, current_app, g, session, websocket
from quart_security import SecurityState, current_user
from sqlalchemy import Column, DateTime, ForeignKey, Integer, Text, delete, select

import stk.extensions as ext
from stk.extensions import Base
from stk.user.models import User

# ponytail: polling, so delivery lags up to POLL seconds; on Postgres add a
# LISTEN wake-up to the same loop if that lag is noticed.
POLL = 0.25
# Rows are re-read for this long, so one that commits after a later id is still
# delivered (Postgres ids can commit out of order); seen ids are skipped.
WINDOW = timedelta(seconds=10)
RETENTION = timedelta(minutes=1)

ws_bp = Blueprint("ws", __name__)
_clients: dict[str, set[asyncio.Queue]] = {}
_poller: asyncio.Task | None = None


class Message(Base):
    __tablename__ = "stk_message"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), nullable=False)
    payload = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)


def get_connected_users() -> list[str]:
    return list(_clients)


async def broadcast(message: dict, user_id, session=None):
    """Send only to the explicitly selected user, from any process.

    With `session`, the message joins that transaction: it goes out at commit and
    not at all on rollback. Without it, it is committed on its own session.
    """
    row = Message(user_id=int(user_id), payload=json.dumps(message))
    if session is not None:
        session.add(row)
        return
    async with ext.async_session_factory() as db:
        db.add(row)
        await db.commit()


def _deliver(user_id: str, payload: str):
    for queue in _clients.get(user_id, set()):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # Disconnect slow consumers instead of retaining an unbounded backlog.
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(None)


async def _recent_ids(db):
    since = datetime.now() - WINDOW
    return (
        await db.execute(
            select(Message.id, Message.user_id).where(Message.created_at > since)
        )
    ).all()


async def _poll():
    """Fan new rows out to this process's sockets until the last one closes."""
    global _poller
    try:
        async with ext.async_session_factory() as db:
            # Only rows sent from now on: a reconnecting tab must not replay.
            seen = {row.id: time.monotonic() for row in await _recent_ids(db)}
        trimmed = time.monotonic()
        while _clients:
            await asyncio.sleep(POLL)
            now = time.monotonic()
            async with ext.async_session_factory() as db:
                # Every new row counts as seen, so a user who connects later does
                # not receive what was sent before.
                fresh = [row for row in await _recent_ids(db) if row.id not in seen]
                seen.update((row.id, now) for row in fresh)
                wanted = [row.id for row in fresh if str(row.user_id) in _clients]
                rows = []
                if wanted:
                    query = select(Message.user_id, Message.payload)
                    query = query.where(Message.id.in_(wanted)).order_by(Message.id)
                    rows = (await db.execute(query)).all()
                if now - trimmed > RETENTION.total_seconds():
                    cutoff = datetime.now() - RETENTION
                    await db.execute(delete(Message).where(Message.created_at < cutoff))
                    await db.commit()
                    trimmed = now
            for row in rows:
                _deliver(str(row.user_id), row.payload)
            horizon = now - 2 * WINDOW.total_seconds()
            seen = {id: at for id, at in seen.items() if at > horizon}
    except Exception:
        # Open sockets stop receiving until the next one connects and restarts this.
        logging.getLogger(__name__).exception("websocket message poller failed")
        raise
    finally:
        _poller = None


@ws_bp.websocket("/ws")
async def ws_endpoint():
    db = g.pop("db_session", None)
    if db is not None:
        await db.close()
    allowed = current_app.config.get("STK_WS_ALLOWED_ORIGINS") or [
        (current_app.config.get("STK_PUBLIC_URL") or "").rstrip("/")
        or websocket.host_url.replace("ws://", "http://", 1)
        .replace("wss://", "https://", 1)
        .rstrip("/")
    ]
    if websocket.headers.get("Origin") not in allowed:
        await websocket.close(4003, "Invalid origin")
        return
    if not current_user.is_authenticated:
        await websocket.close(4001, "Unauthorized")
        return
    user_id, uniquifier, token = (
        str(current_user.id),
        current_user.get_id(),
        session.get("_id"),
    )
    if len(_clients.get(user_id, ())) >= current_app.config.get(
        "STK_WS_CONNECTIONS_PER_USER", 5
    ) or sum(map(len, _clients.values())) >= current_app.config.get(
        "STK_WS_MAX_CONNECTIONS", 1000
    ):
        await websocket.close(4008, "Connection limit")
        return
    queue = asyncio.Queue(maxsize=current_app.config.get("STK_WS_QUEUE_SIZE", 32))
    _clients.setdefault(user_id, set()).add(queue)
    global _poller
    if _poller is None:
        _poller = asyncio.create_task(_poll())

    async def check_authorization():
        async with ext.async_session_factory() as db:
            state = await db.scalar(
                select(SecurityState.payload).where(
                    SecurityState.token == token,
                    SecurityState.expires_at > int(time.time()),
                )
            )
            user = await db.scalar(
                select(User.id).where(
                    User.fs_uniquifier == uniquifier, User.active.is_(True)
                )
            )
            return bool(user and state and state.get("user_id") == uniquifier)

    async def authorized():
        check = asyncio.create_task(check_authorization())
        try:
            return await asyncio.shield(check)
        except asyncio.CancelledError:
            await check
            raise

    async def sender():
        while True:
            message = await queue.get()
            if message is None or not await authorized():
                await websocket.close(4001, "Session ended")
                return
            await websocket.send(message)

    async def receiver():
        started, count = time.monotonic(), 0
        while True:
            message = await websocket.receive()
            if time.monotonic() - started >= 60:
                started, count = time.monotonic(), 0
            count += 1
            if count > current_app.config.get("STK_WS_MESSAGE_LIMIT", 60) or len(
                message
            ) > current_app.config.get("STK_WS_MESSAGE_SIZE", 65536):
                await websocket.close(4008, "Message limit")
                return

    async def monitor():
        while True:
            await asyncio.sleep(current_app.config.get("STK_WS_AUTH_INTERVAL", 5))
            if not await authorized():
                await websocket.close(4001, "Session ended")
                return

    tasks = []
    try:
        await websocket.send(json.dumps({"type": "connected", "user_id": user_id}))
        tasks = [
            asyncio.create_task(sender()),
            asyncio.create_task(receiver()),
            asyncio.create_task(monitor()),
        ]
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        _clients[user_id].discard(queue)
        if not _clients[user_id]:
            del _clients[user_id]
