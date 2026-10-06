"""Host controls for all routes and server-side session transitions."""

import secrets
from datetime import datetime
from urllib.parse import urlsplit

from quart import abort, g, request, session
from quart_security import SecurityState, current_user
from quart_security.breach import password_is_breached
from quart_security.password import validate_password
from sqlalchemy import delete, select

from stk.user.models import Session


def register_security_controls(app):
    @app.before_request
    async def protect_request():
        public_url = app.config.get("STK_PUBLIC_URL")
        if (
            public_url
            and request.path != "/health"
            and request.host != urlsplit(public_url).netloc
        ):
            abort(400, description="Invalid host")
        g.previous_auth_token = session.get("_id")
        g.previous_second_factor = session.get("tf_user_id")
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            expected = session.get("_csrf_token")
            supplied = request.headers.get("X-CSRFToken")
            if not supplied:
                supplied = (await request.form).get("csrf_token")
            if not supplied:
                body = await request.get_json(silent=True)
                supplied = body.get("csrf_token") if isinstance(body, dict) else None
            if (
                not isinstance(expected, str)
                or not isinstance(supplied, str)
                or not secrets.compare_digest(expected, supplied)
            ):
                abort(400, description="Invalid CSRF token")
            if request.path.startswith("/api/") and request.method in {
                "POST",
                "PUT",
                "PATCH",
            }:
                body = await request.get_json(silent=True)
                if not isinstance(body, dict) or (
                    "item" in body and not isinstance(body["item"], dict)
                ):
                    abort(400, description="Expected a JSON object")
        if request.path.startswith("/api/"):
            for name, low, high in (("page", 1, 100000), ("per_page", 1, 100)):
                if name in request.args:
                    try:
                        value = int(request.args[name])
                    except ValueError:
                        abort(400, description="Invalid pagination")
                    if not low <= value <= high:
                        abort(400, description="Invalid pagination")

    @app.after_request
    async def synchronize_session(response):
        if session.get("_csrf_token") or session.get("_id"):
            response.headers.setdefault("Cache-Control", "private, no-store")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault(
            "Content-Security-Policy",
            "frame-ancestors 'none'; base-uri 'self'; object-src 'none'",
        )
        if "previous_auth_token" not in g:
            return response
        previous = g.get("previous_auth_token")
        token = session.get("_id")
        if previous != token or g.get("previous_second_factor") != session.get(
            "tf_user_id"
        ):
            interface = app.session_interface
            if hasattr(session, "sid"):
                await interface.delete(key=interface.key_prefix + session.sid, app=app)
                session.sid = secrets.token_urlsafe(32)
                session.modified = True
            db = g.get("db_session")
            if db is not None:
                old = None
                if previous and previous != token:
                    await db.execute(
                        delete(SecurityState).where(SecurityState.token == previous)
                    )
                    old = await db.scalar(
                        select(Session).where(Session.session_token == previous)
                    )
                    if old:
                        old.is_active = False
                if token and current_user.is_authenticated:
                    record = await db.scalar(
                        select(Session).where(Session.session_token == token)
                    )
                    if record is None:
                        record = await Session.create_session(
                            current_user.id,
                            token,
                            request.remote_addr,
                            meta=old.meta if old else None,
                        )
                    record.expires_at = datetime.now() + app.permanent_session_lifetime
                await db.commit()
        return response


async def check_password_policy(password):
    from quart import current_app

    if not isinstance(password, str) or len(password) > 1024:
        abort(400, description="Invalid password")
    errors = validate_password(
        password, min_length=current_app.config["SECURITY_PASSWORD_LENGTH_MIN"]
    )
    if errors:
        abort(400, description=errors[0])
    if current_app.config.get("SECURITY_PASSWORD_BREACH_CHECK", True):
        breached = await password_is_breached(
            password,
            count_min=current_app.config.get("SECURITY_PASSWORD_BREACH_COUNT_MIN", 1),
        )
        if breached:
            abort(
                400, description="Choose a password that has not appeared in a breach"
            )
