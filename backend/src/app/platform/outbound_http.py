"""The real `OutboundHttp`: one client, one User-Agent, one set of safety rules.

Every request resolves its host first and refuses anything that is not a public
address (loopback, private ranges, link-local including cloud metadata, carrier-grade
NAT, multicast and reserved space). The connection is then made to the address that
was checked, with the real host kept for the `Host` header and certificate check, so
a name that resolves differently a moment later cannot slip past the check. Redirects
are followed by hand so each hop gets the same treatment.
"""

import asyncio
import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx2

from app.platform.app_info import load_app_info
from app.platform.config.outbound_http import get_outbound_http_settings
from app.shared_kernel.outbound_http import (
    OutboundFailure,
    OutboundHttpError,
    OutboundResponse,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from app.platform.config.outbound_http import OutboundHttpSettings

PROJECT_URL = "https://github.com/samcorky/menagerist"
MAX_REDIRECTS = 5

type Resolver = Callable[[str, int], Awaitable[list[str]]]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
# Ranges that embed an IPv4 address and are routed to it by a gateway, so the
# embedded address would need checking too. Nothing here needs them, so refuse them.
_EMBEDDING_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16")
)


def build_user_agent(version: str, contact: str = "", note: str = "") -> str:
    """`Menagerist/<version> (+<project url>[; contact: <contact>][; <note>])`."""
    parts = [f"+{PROJECT_URL}"]
    if contact:
        parts.append(f"contact: {contact}")
    if note:
        parts.append(note)
    return f"Menagerist/{version} ({'; '.join(parts)})"


def is_public_address(address: str) -> bool:
    """Whether `address` is somewhere on the public internet."""
    try:
        ip = ipaddress.ip_address(address.partition("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_global
        and not ip.is_multicast
        and not any(
            ip in network
            for network in _EMBEDDING_NETWORKS
            if network.version == ip.version
        )
    )


async def resolve_host(host: str, port: int) -> list[str]:
    """Every address the system resolver gives `host`."""
    try:
        found = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise OutboundHttpError(OutboundFailure.NETWORK) from exc
    return list(dict.fromkeys(str(entry[4][0]) for entry in found))


class HttpxOutboundHttp:
    """Reads over HTTP(S) from public addresses, within the configured limits."""

    def __init__(
        self,
        settings: OutboundHttpSettings,
        *,
        version: str,
        resolver: Resolver = resolve_host,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._user_agent = build_user_agent(
            version, settings.contact, settings.user_agent_note
        )
        self._resolver = resolver
        self._transport = transport

    @property
    def user_agent(self) -> str:
        """The User-Agent sent with every request."""
        return self._user_agent

    async def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        params: Mapping[str, str | int] | None = None,
        max_bytes: int | None = None,
    ) -> OutboundResponse:
        """Fetch `url` from the public internet, re-checking every redirect hop."""
        cap = self._settings.max_response_bytes
        limit = min(max_bytes, cap) if max_bytes else cap
        sent = {"Accept-Encoding": "identity", **(headers or {})}
        sent["User-Agent"] = self._user_agent
        try:
            target = httpx2.URL(url, params=params)
        except (httpx2.InvalidURL, ValueError) as exc:
            raise OutboundHttpError(OutboundFailure.INVALID_URL) from exc
        timeout = httpx2.Timeout(
            self._settings.read_timeout_seconds,
            connect=self._settings.connect_timeout_seconds,
        )
        async with httpx2.AsyncClient(
            timeout=timeout,
            transport=self._transport,
            follow_redirects=False,
            trust_env=False,
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                response = await self._hop(client, target, sent, limit)
                location = response.headers.get("location")
                if response.status not in _REDIRECT_STATUSES or location is None:
                    return response
                target = self._next(target, location, sent)
        raise OutboundHttpError(OutboundFailure.TOO_MANY_REDIRECTS)

    @staticmethod
    def _next(current: httpx2.URL, location: str, sent: dict[str, str]) -> httpx2.URL:
        try:
            following = httpx2.URL(urljoin(str(current), location))
        except (httpx2.InvalidURL, ValueError) as exc:
            raise OutboundHttpError(OutboundFailure.INVALID_URL) from exc
        if current.scheme == "https" and following.scheme != "https":
            raise OutboundHttpError(OutboundFailure.INVALID_URL)
        if following.host != current.host:
            for name in [name for name in sent if name.lower() in _CREDENTIAL_HEADERS]:
                del sent[name]
        return following

    async def _hop(
        self,
        client: httpx2.AsyncClient,
        target: httpx2.URL,
        headers: Mapping[str, str],
        limit: int,
    ) -> OutboundResponse:
        address = await self._vetted_address(target)
        try:
            async with client.stream(
                "GET",
                target.copy_with(host=address),
                headers={**headers, "Host": target.netloc.decode("ascii")},
                extensions={"sni_hostname": target.host},
            ) as response:
                body = await _read_bounded(response, limit)
                return OutboundResponse(
                    url=str(target),
                    status=response.status_code,
                    headers={k.lower(): v for k, v in response.headers.items()},
                    body=body,
                )
        except httpx2.TimeoutException as exc:
            raise OutboundHttpError(OutboundFailure.TIMEOUT) from exc
        except httpx2.HTTPError as exc:
            raise OutboundHttpError(OutboundFailure.NETWORK) from exc

    async def _vetted_address(self, target: httpx2.URL) -> str:
        """The address to connect to, once every address `target` names is public."""
        if target.scheme not in _DEFAULT_PORTS or not target.host:
            raise OutboundHttpError(OutboundFailure.INVALID_URL)
        port = target.port or _DEFAULT_PORTS[target.scheme]
        addresses = (
            [target.host]
            if _is_ip_literal(target.host)
            else await self._resolver(target.host, port)
        )
        if not addresses:
            raise OutboundHttpError(OutboundFailure.NETWORK)
        if not all(is_public_address(address) for address in addresses):
            raise OutboundHttpError(OutboundFailure.BLOCKED_ADDRESS)
        return addresses[0]


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return False
    return True


async def _read_bounded(response: httpx2.Response, limit: int) -> bytes:
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > limit:
        raise OutboundHttpError(OutboundFailure.TOO_LARGE)
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise OutboundHttpError(OutboundFailure.TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


def outbound_http() -> HttpxOutboundHttp:
    """The client every outbound request goes through, set up from the settings."""
    return HttpxOutboundHttp(
        get_outbound_http_settings(), version=load_app_info().version
    )
