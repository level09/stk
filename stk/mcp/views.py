"""The `/mcp` endpoint, authenticated by bearer token, and the page where a user
creates and revokes their tokens."""

from datetime import datetime

from quart import Blueprint, Response, current_app, g, render_template, request
from quart_security import auth_required, current_user
from sqlalchemy import select

import stk.extensions as ext
from stk.mcp import server
from stk.mcp.models import McpToken
from stk.security import csrf_exempt
from stk.user.models import Activity, User
from stk.utils.ratelimit import consume_limit

bp_mcp = Blueprint("mcp", __name__)


def base_url():
    return (current_app.config.get("STK_PUBLIC_URL") or request.host_url).rstrip("/")


async def authenticate(header):
    """The caller behind a bearer token, or None. The user's roles are read on
    every request, so a role change or deactivation applies to the next call."""
    if not header or not header.startswith("Bearer "):
        return None
    db = g.db_session
    token = await db.scalar(
        select(McpToken).where(
            McpToken.token_hash == McpToken.digest(header[7:].strip())
        )
    )
    if token is None or token.expires_at <= datetime.now():
        return None
    user = await db.get(User, token.user_id)
    if user is None or not user.active or user.fs_uniquifier != token.user_uniquifier:
        return None
    token.last_used_at = datetime.now()
    await db.commit()
    # quart-security keeps the request's user here; setting it makes the tool
    # run as this user without touching the session cookie.
    g._current_user = user
    scopes = frozenset(token.scopes) & {role.name for role in user.roles}
    return server.Caller(user=user, token=token, scopes=scopes)


# ponytail: static bearer tokens only, no OAuth authorization server; clients
# that need RFC 9728 discovery and a consent flow need one built in front of this.
@bp_mcp.post("/mcp")
@csrf_exempt
async def mcp():
    origin = request.headers.get("Origin")
    if origin is not None and origin != base_url():
        # DNS rebinding guard the transport spec requires.
        return server.error(None, server.FORBIDDEN, "Origin not allowed", 403)
    caller = await authenticate(request.headers.get("Authorization"))
    if caller is None:
        challenge = 'Bearer realm="mcp"'
        if request.headers.get("Authorization"):
            challenge += ', error="invalid_token"'
        return Response("", status=401, headers={"WWW-Authenticate": challenge})
    if current_app.config.get("QUART_RATE_LIMITER_ENABLED", True) and not (
        await consume_limit(
            ext.async_session_factory,
            f"mcp:{caller.token.id}",
            current_app.config.get("STK_MCP_REQUEST_LIMIT", 120),
            60,
        )
    ):
        return server.error(None, server.RATE_LIMITED, "Rate limit exceeded", 429)
    body = await request.get_json(silent=True)
    return await server.dispatch(caller, body, request.headers)


@bp_mcp.get("/tokens/")
@auth_required("session")
async def tokens():
    rows = await g.db_session.scalars(
        select(McpToken)
        .where(McpToken.user_id == current_user.id)
        .order_by(McpToken.created_at.desc())
    )
    page = {
        "tokens": [row.to_dict() for row in rows],
        "roles": sorted(role.name for role in current_user.roles),
        "url": base_url() + "/mcp",
    }
    return await render_template("mcp/tokens.html", page=page)


@bp_mcp.post("/api/token/")
@auth_required("session", fresh=True)
async def create_token():
    item = (await request.json).get("item", {})
    name = item.get("name")
    scopes = item.get("scopes", [])
    if not isinstance(name, str) or not 0 < len(name.strip()) <= 80:
        return {"message": "Name is required, at most 80 characters"}, 400
    own = {role.name for role in current_user.roles}
    if not isinstance(scopes, list) or not all(s in own for s in scopes):
        return {"message": "Scopes must be roles you hold"}, 400
    row, secret = McpToken.issue(current_user, name.strip(), sorted(set(scopes)))
    g.db_session.add(row)
    await g.db_session.flush()
    await Activity.register(current_user.id, "MCP Token Create", row.to_dict())
    await g.db_session.commit()
    return {"message": "Token created", "token": secret, "item": row.to_dict()}


@bp_mcp.delete("/api/token/<int:id>")
@auth_required("session")
async def revoke_token(id):
    row = await g.db_session.get(McpToken, id)
    if row is None or row.user_id != current_user.id:
        return {"message": "Token not found"}, 404
    data = row.to_dict()
    await g.db_session.delete(row)
    await Activity.register(current_user.id, "MCP Token Revoke", data)
    await g.db_session.commit()
    return {"message": "Token revoked"}
