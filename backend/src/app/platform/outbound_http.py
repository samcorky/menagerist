"""The real `OutboundHttp`: one client, one User-Agent, one set of safety rules.

Every request resolves its host first and refuses anything that is not a public
address (loopback, private ranges, link-local including cloud metadata, carrier-grade
NAT, multicast and reserved space). The connection is then made to the address that
was checked, with the real host kept for the `Host` header and certificate check, so
a name that resolves differently a moment later cannot slip past the check. Redirects
are followed by hand so each hop gets the same treatment.

When a proxy is configured (`HTTP_PROXY`, `HTTPS_PROXY`, minus hosts in `NO_PROXY`),
the connection is still pinned by default: the proxy is asked to connect to the
checked address, so a name that answers differently to the proxy cannot slip past, and
a name this host cannot resolve is refused. With pinning off the proxy resolves the
name itself and is the enforcement point; a name this host cannot resolve is then
refused unless the settings allow it. Only the settings configure a proxy: the HTTP
library never reads the environment itself.

A host the administrator lists in `MENAGERIST_HTTP_TRUSTED_HOSTS` may resolve to a
private (RFC 1918 or unique local) address, but only for a caller that says the
destination was admin-configured. Every address it resolves to must be allowed, the
connection is still pinned, each redirect hop is judged afresh, and a request that
used the allowance is logged. Loopback, link-local and the other floor ranges are
refused regardless.

A whole request, redirects included, must finish within a total deadline. Each address
a name resolves to is tried in order, and refusals and failures are logged at warning
level with the host and address but never the query string or credentials.
"""

import asyncio
import ipaddress
import socket
from typing import TYPE_CHECKING
from urllib.parse import urljoin

import httpx2
import structlog

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

logger = structlog.get_logger()

PROJECT_URL = "https://github.com/samcorky/menagerist"
MAX_REDIRECTS = 5

type Resolver = Callable[[str, int], Awaitable[list[str]]]
type ProxyTransportFactory = Callable[[str], httpx2.AsyncBaseTransport]

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_CREDENTIAL_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})
_DEFAULT_PORTS = {"http": 80, "https": 443}
# Ranges that embed an IPv4 address and are routed to it by a gateway, so the
# embedded address would need checking too. Nothing here needs them, so refuse them.
_EMBEDDING_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16")
)


# The only private ranges a trusted host may resolve to. Loopback, link-local
# (cloud metadata), multicast and the rest stay refused whatever the settings say.
_TRUSTABLE_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


def build_user_agent(version: str, contact: str = "", note: str = "") -> str:
    """`Menagerist/<version> (+<project url>[; contact: <contact>][; <note>])`."""
    parts = [f"+{PROJECT_URL}"]
    if contact:
        parts.append(f"contact: {contact}")
    if note:
        parts.append(note)
    return f"Menagerist/{version} ({'; '.join(parts)})"


def bypasses_proxy(host: str, no_proxy: str) -> bool:
    """Whether `host` is listed in a `NO_PROXY` value.

    Entries are `*`, host names or domains (which also match subdomains, with or
    without a leading dot), IP addresses and network ranges.
    """
    name = host.lower().strip("[]")
    try:
        ip = ipaddress.ip_address(name)
    except ValueError:
        ip = None
    for raw in no_proxy.split(","):
        entry = raw.strip().lower()
        if entry == "*":
            return True
        if entry and ip is not None and _in_network(ip, entry):
            return True
        domain = entry.lstrip(".")
        if domain and (name == domain or name.endswith(f".{domain}")):
            return True
    return False


def _in_network(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, entry: str) -> bool:
    try:
        return ip in ipaddress.ip_network(entry, strict=False)
    except ValueError:
        return False


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


def is_trusted_private_address(address: str) -> bool:
    """Whether `address` is in a range an administrator may trust (RFC 1918, ULA)."""
    try:
        ip = ipaddress.ip_address(address.partition("%")[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in n for n in _TRUSTABLE_NETWORKS if n.version == ip.version)


def refusal_rule(address: str) -> str:
    """Which rule makes `address` non-public, for the log; `public` when none does."""
    try:
        ip = ipaddress.ip_address(address.partition("%")[0])
    except ValueError:
        return "not_an_address"
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    rules = (
        ("loopback", ip.is_loopback),
        ("link_local", ip.is_link_local),
        ("multicast", ip.is_multicast),
        ("private", ip.is_private and not ip.is_unspecified),
        ("unspecified", ip.is_unspecified),
        (
            "embeds_ipv4",
            any(ip in n for n in _EMBEDDING_NETWORKS if n.version == ip.version),
        ),
        ("not_global", not ip.is_global),
    )
    return next((name for name, hit in rules if hit), "public")


async def resolve_host(host: str, port: int) -> list[str]:
    """Every address the system resolver gives `host`."""
    try:
        found = await asyncio.get_running_loop().getaddrinfo(
            host, port, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise OutboundHttpError(OutboundFailure.NETWORK) from exc
    return list(dict.fromkeys(str(entry[4][0]) for entry in found))


def _proxy_transport(proxy: str) -> httpx2.AsyncBaseTransport:
    return httpx2.AsyncHTTPTransport(proxy=proxy)


class HttpxOutboundHttp:
    """Reads over HTTP(S) from public addresses, within the configured limits."""

    def __init__(
        self,
        settings: OutboundHttpSettings,
        *,
        version: str,
        resolver: Resolver = resolve_host,
        transport: httpx2.AsyncBaseTransport | None = None,
        proxy_transport: ProxyTransportFactory = _proxy_transport,
    ) -> None:
        self._settings = settings
        self._user_agent = build_user_agent(
            version, settings.contact, settings.user_agent_note
        )
        self._resolver = resolver
        self._transport = transport
        self._proxy_transport = proxy_transport

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
        admin_configured: bool = False,
    ) -> OutboundResponse:
        """Fetch `url` from the public internet, re-checking every redirect hop.

        A host in the trusted list may also resolve to a private address, but only
        when the caller says an administrator configured the destination.
        """
        cap = self._settings.max_response_bytes
        limit = min(max_bytes, cap) if max_bytes else cap
        sent = {"Accept-Encoding": "identity", **(headers or {})}
        sent["User-Agent"] = self._user_agent
        try:
            target = httpx2.URL(url, params=params)
        except (httpx2.InvalidURL, ValueError) as exc:
            raise OutboundHttpError(OutboundFailure.INVALID_URL) from exc
        return await self._follow(target, sent, limit, admin_configured)

    async def _follow(
        self,
        target: httpx2.URL,
        sent: dict[str, str],
        limit: int,
        admin_configured: bool,
    ) -> OutboundResponse:
        """Follow redirects by hand inside one deadline, logging what fails."""
        failure = OutboundFailure.TOO_MANY_REDIRECTS
        try:
            async with asyncio.timeout(self._settings.total_timeout_seconds):
                for _ in range(MAX_REDIRECTS + 1):
                    response = await self._hop(target, sent, limit, admin_configured)
                    logger.debug(
                        "outbound_hop_completed",
                        scheme=target.scheme,
                        host=target.host,
                        port=target.port,
                        status=response.status,
                    )
                    location = response.headers.get("location")
                    if response.status not in _REDIRECT_STATUSES or location is None:
                        return response
                    previous = target
                    target = self._next(target, location, sent)
                    logger.debug(
                        "outbound_redirect_followed",
                        from_host=previous.host,
                        to_host=target.host,
                        status=response.status,
                    )
        except TimeoutError as exc:
            failure = OutboundFailure.TIMEOUT
            _log_failure(target, failure)
            raise OutboundHttpError(failure) from exc
        except OutboundHttpError as exc:
            if exc.failure is not OutboundFailure.BLOCKED_ADDRESS:
                _log_failure(target, exc.failure)
            raise
        _log_failure(target, failure)
        raise OutboundHttpError(failure)

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
        target: httpx2.URL,
        headers: Mapping[str, str],
        limit: int,
        admin_configured: bool,
    ) -> OutboundResponse:
        port = self._checked_port(target)
        trusted = admin_configured and self._is_trusted(target, port)
        proxy = self._proxy_for(target)
        pin = proxy is None or self._settings.http_proxy_pin_addresses
        if pin:
            vetted = await self._vetted_addresses(target, port, trusted=trusted)
            # Behind a proxy the proxy makes the connection, so a second address
            # cannot be tried here.
            candidates: list[str | None] = list(vetted if proxy is None else vetted[:1])
        else:
            await self._vet_before_proxy(target, port, trusted=trusted)
            candidates = [None]
        logger.debug(
            "outbound_hop_started",
            scheme=target.scheme,
            host=target.host,
            via_proxy=proxy is not None,
            pinned=pin,
            addresses=[address for address in candidates if address],
        )
        transport = self._transport if proxy is None else self._proxy_transport(proxy)
        timeout = httpx2.Timeout(
            self._settings.read_timeout_seconds,
            connect=self._settings.connect_timeout_seconds,
        )
        unreachable: httpx2.HTTPError | None = None
        for address in candidates:
            if address is None:
                request_url, request_headers, extensions = target, dict(headers), {}
            else:
                request_url = target.copy_with(host=address)
                request_headers = {**headers, "Host": target.netloc.decode("ascii")}
                extensions = {"sni_hostname": target.host}
            try:
                return await self._send(
                    request_url,
                    request_headers,
                    extensions,
                    transport,
                    timeout,
                    limit,
                    target,
                )
            except (httpx2.ConnectError, httpx2.ConnectTimeout) as exc:
                unreachable = exc
                logger.warning(
                    "outbound_address_unreachable",
                    host=target.host,
                    address=address,
                )
            except httpx2.TimeoutException as exc:
                raise OutboundHttpError(OutboundFailure.TIMEOUT) from exc
            except httpx2.HTTPError as exc:
                raise OutboundHttpError(OutboundFailure.NETWORK) from exc
        if isinstance(unreachable, httpx2.TimeoutException):
            raise OutboundHttpError(OutboundFailure.TIMEOUT) from unreachable
        raise OutboundHttpError(OutboundFailure.NETWORK) from unreachable

    @staticmethod
    async def _send(
        request_url: httpx2.URL,
        headers: Mapping[str, str],
        extensions: dict[str, str],
        transport: httpx2.AsyncBaseTransport | None,
        timeout: httpx2.Timeout,
        limit: int,
        target: httpx2.URL,
    ) -> OutboundResponse:
        async with (
            httpx2.AsyncClient(
                timeout=timeout,
                transport=transport,
                follow_redirects=False,
                trust_env=False,
            ) as client,
            client.stream(
                "GET", request_url, headers=headers, extensions=extensions
            ) as response,
        ):
            body = await _read_bounded(response, limit)
            return OutboundResponse(
                url=str(target),
                status=response.status_code,
                headers={k.lower(): v for k, v in response.headers.items()},
                body=body,
            )

    def _proxy_for(self, target: httpx2.URL) -> str | None:
        """The proxy `target` goes through, if one is set and it is not exempt."""
        if bypasses_proxy(target.host, self._settings.no_proxy):
            return None
        secret = (
            self._settings.https_proxy
            if target.scheme == "https"
            else self._settings.http_proxy
        )
        return secret.get_secret_value() if secret else None

    @staticmethod
    def _checked_port(target: httpx2.URL) -> int:
        if target.scheme not in _DEFAULT_PORTS or not target.host:
            raise OutboundHttpError(OutboundFailure.INVALID_URL)
        return target.port or _DEFAULT_PORTS[target.scheme]

    async def _addresses(self, target: httpx2.URL, port: int) -> list[str]:
        if _is_ip_literal(target.host):
            return [target.host]
        return await self._resolver(target.host, port)

    def _is_trusted(self, target: httpx2.URL, port: int) -> bool:
        """Whether the administrator listed this exact host (and port, if given)."""
        if _is_ip_literal(target.host):
            return False
        entries = self._settings.trusted_host_entries
        host = target.host.lower()
        return host in entries or f"{host}:{port}" in entries

    async def _vetted_addresses(
        self, target: httpx2.URL, port: int, *, trusted: bool
    ) -> list[str]:
        """The addresses to try, once every address `target` names is public."""
        addresses = await self._addresses(target, port)
        if not addresses:
            raise OutboundHttpError(OutboundFailure.NETWORK)
        _refuse_non_public(target, addresses, trusted=trusted)
        return addresses

    async def _vet_before_proxy(
        self, target: httpx2.URL, port: int, *, trusted: bool
    ) -> None:
        """Vet a name the proxy will resolve itself, as it will not be pinned.

        A name this host cannot resolve is refused unless the settings leave it to the
        proxy, for a network where the proxy is the only resolver.
        """
        try:
            addresses = await self._addresses(target, port)
        except OutboundHttpError:
            if self._settings.http_proxy_allow_unresolved:
                return
            raise
        _refuse_non_public(target, addresses, trusted=trusted)


def _refuse_non_public(
    target: httpx2.URL, addresses: list[str], *, trusted: bool
) -> None:
    """Refuse the request unless every address is public, or private and trusted."""
    for address in addresses:
        if is_public_address(address):
            continue
        if trusted and is_trusted_private_address(address):
            continue
        logger.warning(
            "outbound_request_refused",
            host=target.host,
            address=address,
            rule=refusal_rule(address),
        )
        raise OutboundHttpError(OutboundFailure.BLOCKED_ADDRESS)
    if trusted and not all(is_public_address(address) for address in addresses):
        logger.warning(
            "outbound_trusted_host_used", host=target.host, addresses=addresses
        )


def _log_failure(target: httpx2.URL, failure: OutboundFailure) -> None:
    logger.warning("outbound_request_failed", host=target.host, failure=failure.value)


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
