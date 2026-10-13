import ipaddress
from typing import TYPE_CHECKING

from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal

if TYPE_CHECKING:
    from collections.abc import Sequence

    from starlette.types import ASGIApp, Receive, Scope, Send

_FORWARDING_HEADERS = (b"x-forwarded-for", b"x-forwarded-proto")


def _is_trusted(host: str | None, trusted: Sequence[str]) -> bool:
    """Mirror Granian's rule: `*`, an address, a network, or a literal name."""
    if "*" in trusted:
        return True
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return host in trusted
    for entry in trusted:
        try:
            if ip in ipaddress.ip_network(entry, strict=False):
                return True
        except ValueError:
            continue
    return False


class ProxyHeaderObserver:
    """Pure ASGI middleware that notes forwarding headers the app is ignoring.

    Sits outside Granian's proxy-header wrapper, so it sees the real peer. It
    only records a time per request; behaviour is unchanged.
    """

    def __init__(self, app: ASGIApp, *, trusted: Sequence[str]) -> None:
        self._app = app
        self._trusted = trusted

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Record untrusted forwarding headers, then pass the request on."""
        if scope["type"] == "http" and any(
            key in _FORWARDING_HEADERS for key, _ in scope["headers"]
        ):
            client = scope.get("client")
            if not _is_trusted(client[0] if client else None, self._trusted):
                proxy_signals.record(ProxySignal.UNTRUSTED_FORWARDING)
        await self._app(scope, receive, send)
