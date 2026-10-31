"""The MCP endpoint: bearer tokens, scopes, and the JSON-RPC roundtrip."""

import unittest
from datetime import datetime, timedelta
from uuid import uuid4

from quart import g
from quart_security import current_user, hash_password
from sqlalchemy import func, select

import stk.extensions as ext
from stk.app import Stk
from stk.mcp import ToolError, tool
from stk.mcp.models import McpToken
from stk.settings import TestingConfig
from stk.user.models import Activity, Base, Role, User


class McpConfig(TestingConfig):
    SECRET_KEY = "test-secret"
    SECURITY_PASSWORD_SALT = "test-salt"


@tool(
    "test.whoami",
    "Echo the caller and a word.",
    {
        "type": "object",
        "properties": {"word": {"type": "string"}},
        "required": ["word"],
        "additionalProperties": False,
    },
)
async def whoami(arguments):
    return {"email": current_user.email, "word": arguments["word"]}


@tool("test.admin", "Admins only.", {"type": "object"}, role="admin")
async def admin_only(arguments):
    return {"ok": True}


@tool("test.refuse", "Writes, then refuses.", {"type": "object"})
async def refuse(arguments):
    g.db_session.add(Role(name="written-then-rolled-back"))
    await g.db_session.flush()
    raise ToolError("Nothing to do")


def rpc(method, params=None, rid=1):
    return {"jsonrpc": "2.0", "id": rid, "method": method, "params": params or {}}


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.app = Stk(__name__, config=McpConfig)
        async with ext.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with ext.async_session_factory() as db:
            admin = User(
                email="admin@example.com",
                active=True,
                password=hash_password("Password123!", app=self.app),
            )
            admin.roles.append(Role(name="admin"))
            db.add(admin)
            await db.commit()
            self.admin_id = admin.id
        self.client = self.app.test_client()

    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def login(self, client):
        await client.get("/login")
        async with client.session_transaction() as cookie:
            csrf = cookie["_csrf_token"]
        response = await client.post(
            "/login",
            form={
                "email": "admin@example.com",
                "password": "Password123!",
                "csrf_token": csrf,
            },
        )
        self.assertEqual(response.status_code, 302)
        # Login clears the session, so the page mints a fresh CSRF token.
        await client.get("/tokens/")
        async with client.session_transaction() as cookie:
            return cookie["_csrf_token"]

    async def create_token(self, scopes):
        client = self.app.test_client()
        csrf = await self.login(client)
        response = await client.post(
            "/api/token/",
            json={"item": {"name": "agent", "scopes": scopes}},
            headers={"X-CSRFToken": csrf},
        )
        return response, client, csrf

    async def token(self, scopes=()):
        response, _, _ = await self.create_token(list(scopes))
        self.assertEqual(response.status_code, 200)
        return (await response.get_json())["token"]

    async def call(self, token, body, headers=None):
        auth = {"Authorization": f"Bearer {token}"} if token else {}
        return await self.client.post("/mcp", json=body, headers=auth | (headers or {}))

    async def scalar(self, query):
        async with ext.async_session_factory() as db:
            return await db.scalar(query)

    async def test_token_is_stored_only_as_its_hash(self):
        secret = await self.token(["admin"])
        self.assertTrue(secret.startswith("stk_mcp_"))
        row = await self.scalar(select(McpToken))
        self.assertEqual(row.token_hash, McpToken.digest(secret))
        self.assertNotIn(secret, str(row.to_dict()))
        self.assertEqual(row.scopes, ["admin"])

    async def test_scopes_are_limited_to_own_roles(self):
        response, _, _ = await self.create_token(["superuser"])
        self.assertEqual(response.status_code, 400)
        self.assertIsNone(await self.scalar(select(McpToken)))

    async def test_unauthenticated_requests_are_rejected(self):
        for token in (None, "stk_mcp_wrong"):
            response = await self.call(token, rpc("tools/list"))
            self.assertEqual(response.status_code, 401)
            self.assertIn("Bearer", response.headers["WWW-Authenticate"])
        # A session cookie is not a credential here: the endpoint skips CSRF.
        client = self.app.test_client()
        await self.login(client)
        response = await client.post("/mcp", json=rpc("tools/list"))
        self.assertEqual(response.status_code, 401)

    async def test_revoked_and_expired_tokens_stop_working(self):
        response, client, csrf = await self.create_token([])
        data = await response.get_json()
        secret, token_id = data["token"], data["item"]["id"]
        self.assertEqual((await self.call(secret, rpc("tools/list"))).status_code, 200)
        response = await client.delete(
            f"/api/token/{token_id}", headers={"X-CSRFToken": csrf}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.call(secret, rpc("tools/list"))).status_code, 401)

        secret = await self.token()
        async with ext.async_session_factory() as db:
            row = await db.scalar(select(McpToken))
            row.expires_at = datetime.now() - timedelta(seconds=1)
            await db.commit()
        self.assertEqual((await self.call(secret, rpc("tools/list"))).status_code, 401)

    async def test_password_change_revokes_tokens(self):
        secret = await self.token()
        self.assertEqual((await self.call(secret, rpc("tools/list"))).status_code, 200)
        async with ext.async_session_factory() as db:
            user = await db.get(User, self.admin_id)
            user.fs_uniquifier = uuid4().hex
            await db.commit()
        self.assertEqual((await self.call(secret, rpc("tools/list"))).status_code, 401)

    async def test_scope_enforcement(self):
        unscoped = await self.token()
        names = {
            t["name"]
            for t in (await (await self.call(unscoped, rpc("tools/list"))).get_json())[
                "result"
            ]["tools"]
        }
        self.assertIn("test.whoami", names)
        self.assertNotIn("test.admin", names)
        response = await self.call(unscoped, rpc("tools/call", {"name": "test.admin"}))
        self.assertEqual(response.status_code, 403)
        self.assertIn(
            "lacks the admin scope", (await response.get_json())["error"]["message"]
        )

        scoped = await self.token(["admin"])
        response = await self.call(scoped, rpc("tools/call", {"name": "test.admin"}))
        self.assertEqual(
            (await response.get_json())["result"]["structuredContent"], {"ok": True}
        )

        # Losing the role revokes the scope on the next call.
        async with ext.async_session_factory() as db:
            admin = await db.get(User, self.admin_id)
            admin.roles = []
            await db.commit()
        response = await self.call(scoped, rpc("tools/call", {"name": "test.admin"}))
        self.assertEqual(response.status_code, 403)
        self.assertIn("does not hold", (await response.get_json())["error"]["message"])

    async def test_legacy_roundtrip(self):
        secret = await self.token()
        init = await (
            await self.call(
                secret, rpc("initialize", {"protocolVersion": "2025-06-18"})
            )
        ).get_json()
        self.assertEqual(init["result"]["protocolVersion"], "2025-06-18")
        notified = await self.call(
            secret, {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )
        self.assertEqual(notified.status_code, 202)

        listed = await (await self.call(secret, rpc("tools/list"))).get_json()
        whoami_tool = next(
            t for t in listed["result"]["tools"] if t["name"] == "test.whoami"
        )
        self.assertEqual(whoami_tool["inputSchema"]["required"], ["word"])

        response = await self.call(
            secret,
            rpc("tools/call", {"name": "test.whoami", "arguments": {"word": "hi"}}),
        )
        result = (await response.get_json())["result"]
        self.assertEqual(
            result["structuredContent"], {"email": "admin@example.com", "word": "hi"}
        )
        self.assertNotIn("isError", result)
        activity = await self.scalar(
            select(Activity).where(Activity.action == "MCP Tool Call")
        )
        self.assertEqual(activity.user_id, self.admin_id)
        self.assertEqual(activity.data["tool"], "test.whoami")
        last_used = await self.scalar(select(McpToken.last_used_at))
        self.assertIsNotNone(last_used)

    async def test_invalid_arguments_and_tool_errors(self):
        secret = await self.token()
        response = await self.call(
            secret,
            rpc("tools/call", {"name": "test.whoami", "arguments": {"word": 3}}),
        )
        result = (await response.get_json())["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Invalid arguments", result["content"][0]["text"])

        response = await self.call(secret, rpc("tools/call", {"name": "test.refuse"}))
        result = (await response.get_json())["result"]
        self.assertEqual(result["content"][0]["text"], "Nothing to do")
        self.assertEqual(
            await self.scalar(
                select(func.count())
                .select_from(Role)
                .where(Role.name == "written-then-rolled-back")
            ),
            0,
        )

        response = await self.call(secret, rpc("tools/call", {"name": "nope"}))
        self.assertEqual((await response.get_json())["error"]["code"], -32602)

    async def test_modern_requests_check_mirrored_headers(self):
        secret = await self.token()
        meta = {"_meta": {"io.modelcontextprotocol/protocolVersion": "2026-07-28"}}
        headers = {
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "server/discover",
        }
        response = await self.call(secret, rpc("server/discover", meta), headers)
        self.assertIn(
            "2026-07-28", (await response.get_json())["result"]["supportedVersions"]
        )

        call = rpc(
            "tools/call", {"name": "test.whoami", "arguments": {"word": "x"}} | meta
        )
        headers = {
            "MCP-Protocol-Version": "2026-07-28",
            "Mcp-Method": "tools/call",
            "Mcp-Name": "test.admin",
        }
        response = await self.call(secret, call, headers)
        self.assertEqual(response.status_code, 400)
        self.assertEqual((await response.get_json())["error"]["code"], -32020)

        response = await self.call(
            secret,
            rpc(
                "tools/list",
                {"_meta": {"io.modelcontextprotocol/protocolVersion": "1900-01-01"}},
            ),
            {"MCP-Protocol-Version": "1900-01-01", "Mcp-Method": "tools/list"},
        )
        self.assertEqual((await response.get_json())["error"]["code"], -32022)

    async def test_foreign_origin_is_refused(self):
        secret = await self.token()
        response = await self.call(
            secret, rpc("tools/list"), {"Origin": "https://evil.example.com"}
        )
        self.assertEqual(response.status_code, 403)

    async def test_tool_registration_fails_fast(self):
        with self.assertRaises(ValueError):
            tool("test.whoami", "Duplicate.", {"type": "object"})
        with self.assertRaises(ValueError):
            tool("has space", "Bad name.", {"type": "object"})
        with self.assertRaises(ValueError):
            tool("test.array", "Not an object.", {"type": "array"})


if __name__ == "__main__":
    unittest.main()
