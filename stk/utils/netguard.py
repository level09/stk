"""Outbound fetches of URLs that users or clients supply. Resolve once, refuse any
non-public address, then connect to that exact IP while TLS (SNI and certificate
checks) still uses the hostname, so DNS rebinding cannot swap in an internal
address between the check and the connection. Every redirect hop is re-checked."""

import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class Blocked(Exception):
    """The fetch was refused: the URL, an address, a redirect or the body size."""


async def _resolve(host: str, port: int) -> list[str]:
    infos = await asyncio.get_running_loop().getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    )
    return sorted({info[4][0] for info in infos})


def _public(addr: str) -> bool:
    ip = ipaddress.ip_address(addr.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    elif ip.version == 6 and ip in _NAT64:
        ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    # is_global counts multicast as global, so it is refused separately.
    return ip.is_global and not ip.is_multicast


def _origin(url: str) -> tuple:
    """(scheme, host, port) with the default port filled in; `_pin` rejects bad ones."""
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = None
    return (
        parts.scheme,
        parts.hostname,
        port or (443 if parts.scheme == "https" else 80),
    )


async def _pin(url: str) -> tuple[str, str, str]:
    """Return (url with the checked IP, Host header, TLS server name)."""
    parts = urlsplit(url)
    host = parts.hostname
    if parts.scheme not in ("http", "https") or not host:
        raise Blocked(f"not an http(s) url: {url!r}")
    if parts.username is not None or parts.password is not None:
        raise Blocked("url carries credentials")
    try:
        port = parts.port
    except ValueError:
        raise Blocked(f"invalid port: {url!r}") from None
    try:
        # Decimal, octal, hex and short forms (2130706433, 0x7f.1, 127.1) mean
        # different things to different parsers; refuse rather than guess.
        socket.inet_aton(host)
        ipaddress.IPv4Address(host)
    except OSError:
        pass
    except ValueError:
        raise Blocked(f"non-canonical IP literal: {host}") from None
    try:
        addrs = await _resolve(host, port or (443 if parts.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError) as exc:
        raise Blocked(f"host does not resolve: {host}") from exc
    if not addrs or not all(_public(a) for a in addrs):
        raise Blocked(f"host resolves to a non-public address: {host}")
    ip = addrs[0]
    netloc = f"[{ip}]" if ":" in ip else ip
    host_header = f"[{host}]" if ":" in host else host
    if port:
        netloc, host_header = f"{netloc}:{port}", f"{host_header}:{port}"
    target = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
    return target, host_header, host


async def fetch(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 10,
    max_bytes: int = 1_048_576,
    max_redirects: int = 5,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> tuple[httpx2.Response, str]:
    """GET a user-supplied URL. Return (response with its body read, final url).

    Raise Blocked when the URL, any resolved address, a redirect or the decoded
    body size is refused, TimeoutError when the whole fetch outlasts `timeout`,
    and httpx2.HTTPError for transport failures. Environment proxies are ignored:
    a proxy would resolve the name itself and undo the pin."""
    headers = dict(headers or {})
    origin = _origin(url)
    async with (
        asyncio.timeout(timeout),
        httpx2.AsyncClient(
            timeout=None, trust_env=False, transport=transport
        ) as client,
    ):
        for _ in range(max_redirects + 1):
            target, host_header, server_name = await _pin(url)
            if _origin(url) != origin:
                # Never hand the caller's credentials to an origin it did not name,
                # including the same host over plain HTTP or another port.
                headers = {
                    k: v
                    for k, v in headers.items()
                    if k.lower() not in ("authorization", "cookie")
                }
            request = client.build_request(
                "GET",
                target,
                headers={**headers, "Host": host_header},
                extensions={"sni_hostname": server_name},
            )
            response = await client.send(request, stream=True)
            # The jar keys cookies by the pinned IP, not the hostname; never carry
            # them across hops.
            client.cookies.clear()
            try:
                if response.has_redirect_location:
                    url = urljoin(url, response.headers["location"])
                    continue
                if int(response.headers.get("content-length") or 0) > max_bytes:
                    raise Blocked(f"response is larger than {max_bytes} bytes")
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body += chunk
                    if len(body) > max_bytes:
                        raise Blocked(f"response is larger than {max_bytes} bytes")
                # What aread() stores; .content, .text and .json() then work.
                response._content = bytes(body)
                return response, url
            finally:
                await response.aclose()
        raise Blocked("too many redirects")
