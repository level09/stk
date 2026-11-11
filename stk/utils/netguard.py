"""Outbound fetches of URLs that users or clients supply. Resolve once, refuse any
non-public address, then connect to that exact IP while TLS (SNI and certificate
checks) still uses the hostname, so DNS rebinding cannot swap in an internal
address between the check and the connection. Every redirect hop is re-checked."""

import asyncio
import ipaddress
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


class Blocked(Exception):
    """The fetch was refused: the URL, an address, a redirect or the body size."""


async def resolve(host: str, port: int) -> list[str]:
    """The addresses `host` resolves to. Tests patch this to fake DNS."""
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
    """(scheme, host, port) with the default port filled in; `pin` rejects bad ones."""
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


async def pin(url: str) -> tuple[str, str, str]:
    """Check a URL and return (url with the checked IP, Host header, TLS server name).

    Raise Blocked unless it is http(s), carries no credentials, and every address
    its host resolves to is public. Connect to the returned URL, send the Host
    header, and use the server name for SNI, so the connection goes to the
    address that was checked. Use it alone to vet a URL another client (a
    headless browser) will open."""
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
        addrs = await resolve(host, port or (443 if parts.scheme == "https" else 80))
    except (socket.gaierror, UnicodeError) as exc:
        raise Blocked(f"host does not resolve: {host}") from exc
    if not addrs or not all(_public(a) for a in addrs):
        raise Blocked(f"host resolves to a non-public address: {host}")
    # ponytail: IPv4 first, since a host without an IPv6 route (a default Docker
    # network) still resolves AAAA records. Try each address in turn if an
    # IPv6-only host ever has to reach a dual-stack one.
    ip = min(addrs, key=lambda a: (":" in a, a))
    netloc = f"[{ip}]" if ":" in ip else ip
    host_header = f"[{host}]" if ":" in host else host
    if port:
        netloc, host_header = f"{netloc}:{port}", f"{host_header}:{port}"
    target = urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, ""))
    return target, host_header, host


def _capped(response: httpx2.Response, max_bytes: int) -> None:
    """Make every read of the body (aread, aiter_bytes/text/lines, .content after
    aread) raise Blocked past `max_bytes` decoded bytes."""
    if int(response.headers.get("content-length") or 0) > max_bytes:
        raise Blocked(f"response is larger than {max_bytes} bytes")
    read = response.aiter_bytes

    async def aiter_bytes(chunk_size=None):
        seen = 0
        async for chunk in read(chunk_size):
            seen += len(chunk)
            if seen > max_bytes:
                raise Blocked(f"response is larger than {max_bytes} bytes")
            yield chunk

    # aread, aiter_text and aiter_lines all read through self.aiter_bytes.
    response.aiter_bytes = aiter_bytes


@asynccontextmanager
async def stream(
    url: str,
    *,
    headers: dict | None = None,
    timeout: float = 10,
    max_bytes: int | None = None,
    max_redirects: int = 5,
    follow_redirects: bool = True,
    transport: httpx2.AsyncBaseTransport | None = None,
) -> AsyncIterator[tuple[httpx2.Response, str]]:
    """GET a user-supplied URL; yield (response with its body unread, final url).

    `timeout` bounds the whole fetch, including reading the body inside the
    block. With `max_bytes`, reading more decoded bytes than that raises
    Blocked. With `follow_redirects=False` a redirect is yielded as is. Raise
    Blocked when the URL, an address or a redirect is refused or there are more
    than `max_redirects`, TimeoutError past `timeout`, and httpx2.HTTPError for
    transport failures. Environment proxies are ignored: a proxy would resolve
    the name itself and undo the pin."""
    headers = dict(headers or {})
    origin = _origin(url)
    async with (
        asyncio.timeout(timeout),
        httpx2.AsyncClient(
            timeout=None, trust_env=False, transport=transport
        ) as client,
    ):
        for _ in range(max_redirects + 1):
            target, host_header, server_name = await pin(url)
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
                if follow_redirects and response.has_redirect_location:
                    url = urljoin(url, response.headers["location"])
                    continue
                if max_bytes is not None:
                    _capped(response, max_bytes)
                yield response, url
                return
            finally:
                await response.aclose()
        raise Blocked("too many redirects")


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

    Same checks and errors as `stream`, with the body read and capped at
    `max_bytes` decoded bytes (default 1 MiB)."""
    async with stream(
        url,
        headers=headers,
        timeout=timeout,
        max_bytes=max_bytes,
        max_redirects=max_redirects,
        transport=transport,
    ) as (response, final_url):
        # A body the transport already loaded (a test's MockTransport) skips the
        # streaming guard; check what was read.
        if len(await response.aread()) > max_bytes:
            raise Blocked(f"response is larger than {max_bytes} bytes")
    return response, final_url
