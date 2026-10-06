"""Atomic rate limits shared by all workers through the application database."""

import hashlib
import time

from quart import abort, request
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

import stk.extensions as ext
from stk.user.models import RateLimitWindow


async def consume_limit(factory, key, limit, seconds):
    now = int(time.time())
    key = f"{hashlib.sha256(key.encode()).hexdigest()}:{now // seconds}"
    async with factory() as db:
        await db.execute(
            delete(RateLimitWindow).where(RateLimitWindow.expires_at <= now)
        )
        try:
            async with db.begin_nested():
                db.add(
                    RateLimitWindow(
                        key=key, count=0, expires_at=(now // seconds + 1) * seconds
                    )
                )
                await db.flush()
        except IntegrityError:
            pass
        result = await db.execute(
            update(RateLimitWindow)
            .where(RateLimitWindow.key == key, RateLimitWindow.count < limit)
            .values(count=RateLimitWindow.count + 1)
        )
        await db.commit()
        return result.rowcount == 1


def register_rate_limits(app):
    @app.before_request
    async def protect_authentication():
        if not app.config.get("QUART_RATE_LIMITER_ENABLED", True):
            return
        oauth_endpoints = {
            "public.google_login",
            "public.google_callback",
            "public.github_login",
            "public.github_callback",
        }
        auth = request.blueprint == "security" or request.endpoint in oauth_endpoints
        if request.endpoint == "security.logout":
            return
        if not auth:
            return
        ip = request.remote_addr or "unknown"
        limit = app.config.get("STK_AUTH_REQUEST_LIMIT", 120)
        if not await consume_limit(ext.async_session_factory, "auth:" + ip, limit, 60):
            abort(429)
        if request.method == "POST" or request.endpoint in oauth_endpoints:
            if not await consume_limit(
                ext.async_session_factory,
                "attempt:" + ip,
                app.config.get("STK_AUTH_ATTEMPT_LIMIT", 10),
                60,
            ):
                abort(429)
