"""Bounded, same-origin WebSockets with periodic session validation."""

import asyncio
import json
import time

from quart import Blueprint, current_app, g, session, websocket
from quart_security import SecurityState, current_user
from sqlalchemy import select

import stk.extensions as ext
from stk.user.models import User

ws_bp = Blueprint("ws", __name__)
_clients: dict[str, set[asyncio.Queue]] = {}


def get_connected_users() -> list[str]:
    return list(_clients)


async def broadcast(message: dict, user_id: str):
    """Send only to the explicitly selected user."""
    payload = json.dumps(message)
    for queue in _clients.get(str(user_id), set()):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            # Disconnect slow consumers instead of retaining an unbounded backlog.
            while not queue.empty():
                queue.get_nowait()
            queue.put_nowait(None)


@ws_bp.websocket("/ws")
async def ws_endpoint():
    db = g.pop("db_session", None)
    if db is not None:
        await db.close()
    allowed = current_app.config.get("STK_WS_ALLOWED_ORIGINS") or [
        current_app.config.get("STK_PUBLIC_URL")
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
