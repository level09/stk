"""Exercise the SSRF guard for user-supplied URLs without touching the network."""

import gzip
import unittest
from unittest import mock

import httpx2

from stk.utils import netguard
from stk.utils.netguard import Blocked, fetch

PUBLIC = "93.184.215.14"


def resolver(table):
    async def resolve(host, port):
        return table[host]

    return mock.patch.object(netguard, "_resolve", resolve)


class NetguardTests(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_every_non_public_address(self):
        addresses = {
            "loopback": "127.0.0.1",
            "loopback6": "::1",
            "private": "10.0.0.5",
            "private192": "192.168.1.1",
            "private6": "fd00::1",
            "metadata": "169.254.169.254",
            "linklocal6": "fe80::1",
            "cgnat": "100.64.0.1",
            "multicast": "224.0.0.1",
            "multicast6": "ff02::1",
            "reserved": "240.0.0.1",
            "broadcast": "255.255.255.255",
            "unspecified": "0.0.0.0",
            "unspecified6": "::",
            "mapped": "::ffff:127.0.0.1",
            "nat64": "64:ff9b::a9fe:a9fe",
            "documentation": "192.0.2.1",
        }
        with resolver({name: [ip] for name, ip in addresses.items()}):
            for name in addresses:
                with self.subTest(name), self.assertRaises(Blocked):
                    await fetch(f"http://{name}/")

    async def test_refuses_when_any_resolved_address_is_private(self):
        with resolver({"mixed.test": [PUBLIC, "10.0.0.1"]}):
            with self.assertRaisesRegex(Blocked, "non-public"):
                await fetch("https://mixed.test/")

    async def test_refuses_ip_literals_without_dns(self):
        for url in (
            "http://127.0.0.1/",
            "http://[::1]:8080/",
            "http://[::ffff:10.0.0.1]/",
        ):
            with self.subTest(url), self.assertRaises(Blocked):
                await fetch(url)

    async def test_refuses_non_canonical_ip_literals(self):
        for host in ("2130706433", "0x7f000001", "017700000001", "127.1", "0x7f.0.0.1"):
            with self.subTest(host), self.assertRaisesRegex(Blocked, "non-canonical"):
                await fetch(f"http://{host}/")

    async def test_refuses_bad_schemes_and_credentials(self):
        for url in (
            "file:///etc/passwd",
            "gopher://example.com/",
            "ftp://example.com/",
            "http:///nohost",
            "http://user:pass@example.com/",
            "http://user@example.com/",
            "http://example.com:99999/",
        ):
            with self.subTest(url), self.assertRaises(Blocked):
                await fetch(url)

    async def test_public_fetch_pins_the_checked_ip(self):
        seen = []

        def handler(request):
            seen.append(request)
            return httpx2.Response(200, json={"ok": True})

        with resolver({"api.example.com": [PUBLIC]}):
            response, final = await fetch(
                "https://api.example.com:8443/hook?x=1",
                transport=httpx2.MockTransport(handler),
            )
        self.assertEqual(response.json(), {"ok": True})
        self.assertEqual(final, "https://api.example.com:8443/hook?x=1")
        request = seen[0]
        self.assertEqual(str(request.url), f"https://{PUBLIC}:8443/hook?x=1")
        self.assertEqual(request.headers["host"], "api.example.com:8443")
        self.assertEqual(request.extensions["sni_hostname"], "api.example.com")

    async def test_redirect_to_private_address_is_refused(self):
        def handler(request):
            return httpx2.Response(302, headers={"location": "http://internal.test/"})

        with resolver({"a.example.com": [PUBLIC], "internal.test": ["10.0.0.7"]}):
            with self.assertRaisesRegex(Blocked, "internal.test"):
                await fetch(
                    "https://a.example.com/", transport=httpx2.MockTransport(handler)
                )

    async def test_redirects_rechecked_and_credentials_dropped(self):
        seen = []

        def handler(request):
            seen.append(request)
            if request.headers["host"] == "a.example.com":
                return httpx2.Response(
                    301, headers={"location": "https://b.example.com/x"}
                )
            return httpx2.Response(200, text="done")

        with resolver({"a.example.com": [PUBLIC], "b.example.com": ["93.184.215.15"]}):
            response, final = await fetch(
                "https://a.example.com/",
                headers={"Authorization": "Bearer t", "Accept": "text/plain"},
                transport=httpx2.MockTransport(handler),
            )
        self.assertEqual(response.text, "done")
        self.assertEqual(final, "https://b.example.com/x")
        self.assertEqual(str(seen[1].url), "https://93.184.215.15/x")
        self.assertNotIn("authorization", seen[1].headers)
        self.assertEqual(seen[1].headers["accept"], "text/plain")

    async def test_credentials_dropped_on_scheme_or_port_change(self):
        for target in ("http://a.example.com/x", "https://a.example.com:8443/x"):
            seen = []

            def handler(request, target=target, seen=seen):
                seen.append(request)
                if len(seen) == 1:
                    return httpx2.Response(302, headers={"location": target})
                return httpx2.Response(200, text="done")

            with self.subTest(target), resolver({"a.example.com": [PUBLIC]}):
                await fetch(
                    "https://a.example.com/",
                    headers={"Authorization": "Bearer t", "Cookie": "s=1"},
                    transport=httpx2.MockTransport(handler),
                )
                self.assertNotIn("authorization", seen[1].headers)
                self.assertNotIn("cookie", seen[1].headers)

    async def test_redirect_limit(self):
        def handler(request):
            return httpx2.Response(302, headers={"location": "/again"})

        with resolver({"loop.example.com": [PUBLIC]}):
            with self.assertRaisesRegex(Blocked, "too many redirects"):
                await fetch(
                    "https://loop.example.com/",
                    max_redirects=3,
                    transport=httpx2.MockTransport(handler),
                )

    async def test_size_cap_counts_decoded_bytes(self):
        bomb = gzip.compress(b"\0" * 10_000)

        def handler(request):
            return httpx2.Response(
                200, content=bomb, headers={"content-encoding": "gzip"}
            )

        with resolver({"big.example.com": [PUBLIC]}):
            with self.assertRaisesRegex(Blocked, "larger than"):
                await fetch(
                    "https://big.example.com/",
                    max_bytes=5_000,
                    transport=httpx2.MockTransport(handler),
                )

    async def test_size_cap_trusts_a_large_content_length(self):
        def handler(request):
            return httpx2.Response(200, content=b"x" * 2_000)

        with resolver({"big.example.com": [PUBLIC]}):
            with self.assertRaisesRegex(Blocked, "larger than"):
                await fetch(
                    "https://big.example.com/",
                    max_bytes=1_000,
                    transport=httpx2.MockTransport(handler),
                )

    async def test_timeout_covers_the_whole_fetch(self):
        async def slow(host, port):
            await netguard.asyncio.sleep(1)

        with mock.patch.object(netguard, "_resolve", slow):
            with self.assertRaises(TimeoutError):
                await fetch("https://slow.example.com/", timeout=0.05)


if __name__ == "__main__":
    unittest.main()
