"""Exercise the explicit CSRF opt-out for signed webhooks."""

import unittest

from quart import Blueprint

import stk.extensions as ext
from stk.app import create_app
from stk.security import csrf_exempt
from stk.settings import TestingConfig


class CsrfConfig(TestingConfig):
    SECURITY_PASSWORD_SALT = "test-salt"


def make_app(config=CsrfConfig):
    app = create_app(config)
    bp = Blueprint("hooks", __name__)

    @bp.post("/webhook")
    @csrf_exempt
    async def webhook():
        return "ok"

    @bp.post("/normal")
    async def normal():
        return "ok"

    app.register_blueprint(bp)
    return app


class CsrfExemptTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self):
        await ext.engine.dispose()

    async def test_exempt_route_skips_token_only(self):
        client = make_app().test_client()
        self.assertEqual((await client.post("/webhook", json={})).status_code, 200)
        self.assertEqual((await client.post("/normal", json={})).status_code, 400)

    async def test_exempt_route_keeps_host_check(self):
        class PublicConfig(CsrfConfig):
            STK_PUBLIC_URL = "https://app.example.com"

        client = make_app(PublicConfig).test_client()
        response = await client.post(
            "/webhook", json={}, headers={"Host": "evil.example.com"}
        )
        self.assertEqual(response.status_code, 400)
