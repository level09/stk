"""Stateless Streamable HTTP JSON-RPC for MCP 2026-07-28: server/discover,
tools/list and tools/call, plus initialize and ping for clients still on the
2025 handshake revisions. Every response is a single JSON object; no sessions,
no SSE, no server-to-client requests."""

import base64
import binascii
import logging
from dataclasses import dataclass

import orjson
from jsonschema.exceptions import best_match
from quart import Response, current_app, g

import stk
from stk.mcp import TOOLS, ToolError
from stk.mcp.models import McpToken
from stk.user.models import Activity, User

log = logging.getLogger(__name__)

PROTOCOL = "2026-07-28"
LEGACY = ("2025-11-25", "2025-06-18", "2025-03-26")
SUPPORTED = (PROTOCOL, *LEGACY)
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
FORBIDDEN = -32001  # implementation-defined range
RATE_LIMITED = -32002
HEADER_MISMATCH = -32020
UNSUPPORTED_VERSION = -32022


@dataclass(frozen=True)
class Caller:
    user: User
    token: McpToken
    scopes: frozenset[str]  # token scopes the user still holds, read per request


def allowed(tool, caller):
    return tool.role is None or tool.role in caller.scopes


def _json(payload, status=200, headers=None):
    return Response(
        orjson.dumps(payload),
        status=status,
        content_type="application/json",
        headers=headers,
    )


def result(rid, value):
    return _json({"jsonrpc": "2.0", "id": rid, "result": value})


def error(rid, code, message, status=200, data=None):
    body = {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}
    if data is not None:
        body["error"]["data"] = data
    return _json(body, status)


def _server_info():
    return {"name": current_app.config["APP_NAME"], "version": stk.__version__}


def _header_value(value):
    """Mcp-Name values may carry =?base64?...?= for non-ASCII."""
    if value and value.startswith("=?base64?") and value.endswith("?="):
        try:
            return base64.b64decode(value[9:-2], validate=True).decode()
        except (binascii.Error, UnicodeDecodeError):
            return None
    return value


async def dispatch(caller, body, headers):
    if (
        not isinstance(body, dict)
        or body.get("jsonrpc") != "2.0"
        or not isinstance(body.get("method"), str)
    ):
        return error(None, INVALID_REQUEST, "Expected one JSON-RPC message", 400)
    if "id" not in body:
        return Response("", status=202)  # notifications need no answer
    rid, method, params = body["id"], body["method"], body.get("params") or {}
    if not isinstance(params, dict):
        return error(rid, INVALID_PARAMS, "params must be an object")
    if method == "initialize":
        asked = params.get("protocolVersion")
        return result(
            rid,
            {
                "protocolVersion": asked if asked in LEGACY else LEGACY[0],
                "capabilities": {"tools": {}},
                "serverInfo": _server_info(),
            },
        )
    meta = params.get("_meta") or {}
    version = meta.get("io.modelcontextprotocol/protocolVersion")
    if version is not None:
        # Modern requests mirror body fields into headers; a mismatch could let a
        # proxy route on one value while we execute another.
        mirrored = {"MCP-Protocol-Version": version, "Mcp-Method": method}
        if method == "tools/call":
            mirrored["Mcp-Name"] = params.get("name")
        for name, want in mirrored.items():
            if _header_value(headers.get(name)) != want:
                return error(rid, HEADER_MISMATCH, f"{name} header mismatch", 400)
    else:
        # 2025-03-26 clients predate the version header.
        version = headers.get("MCP-Protocol-Version", "2025-03-26")
    if version not in SUPPORTED:
        return error(
            rid,
            UNSUPPORTED_VERSION,
            "Unsupported protocol version",
            400,
            data={"supported": list(SUPPORTED), "requested": version},
        )
    if method == "ping":
        return result(rid, {"resultType": "complete"})
    if method == "server/discover":
        return result(
            rid,
            {
                "resultType": "complete",
                "supportedVersions": list(SUPPORTED),
                "capabilities": {"tools": {}},
                "ttlMs": 3_600_000,
                "cacheScope": "public",
                "_meta": {"io.modelcontextprotocol/serverInfo": _server_info()},
            },
        )
    if method == "tools/list":
        tools = [
            {"name": t.name, "description": t.description, "inputSchema": t.schema}
            for t in TOOLS.values()
            if allowed(t, caller)
        ]
        # Private: the list depends on the caller's scopes.
        return result(
            rid,
            {
                "resultType": "complete",
                "tools": tools,
                "ttlMs": 300_000,
                "cacheScope": "private",
            },
        )
    if method == "tools/call":
        return await _call_tool(caller, rid, params)
    return error(rid, METHOD_NOT_FOUND, "Method not found", 404)


def _text(rid, text, is_error=False, structured=None):
    value = {"resultType": "complete", "content": [{"type": "text", "text": text}]}
    if is_error:
        value["isError"] = True
    if isinstance(structured, dict):
        value["structuredContent"] = structured
    return result(rid, value)


async def _call_tool(caller, rid, params):
    name, arguments = params.get("name"), params.get("arguments", {})
    tool = TOOLS.get(name)
    if tool is None:
        return error(rid, INVALID_PARAMS, f"Unknown tool: {name}")
    if not allowed(tool, caller):
        if tool.role in {r.name for r in caller.user.roles}:
            message = f"This token lacks the {tool.role} scope"
        else:
            # A new token would not help: the user lacks the role.
            message = f"The token's user does not hold the {tool.role} role"
        return error(rid, FORBIDDEN, message, 403)
    if not isinstance(arguments, dict):
        return error(rid, INVALID_PARAMS, "arguments must be an object")
    # Read before any rollback expires the rows.
    audit = {"tool": name, "token_id": caller.token.id, "token": caller.token.name}
    user_id, db = caller.user.id, g.db_session
    if (invalid := best_match(tool.validator.iter_errors(arguments))) is not None:
        return _text(rid, f"Invalid arguments: {invalid.message}", is_error=True)
    try:
        value = await tool.fn(arguments)
        text = orjson.dumps(value).decode()
    except ToolError as exc:
        await db.rollback()
        await Activity.register(user_id, "MCP Tool Call", audit | {"error": str(exc)})
        await db.commit()
        return _text(rid, str(exc), is_error=True)
    except Exception:
        log.exception("MCP tool %s failed", name)
        await db.rollback()
        await Activity.register(user_id, "MCP Tool Call", audit | {"error": "failed"})
        await db.commit()
        return _text(rid, "The tool failed; the error is in the server log.", True)
    await Activity.register(user_id, "MCP Tool Call", audit)
    await db.commit()
    return _text(rid, text, structured=value)
