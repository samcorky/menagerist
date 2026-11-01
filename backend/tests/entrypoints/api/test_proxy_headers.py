from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from granian.utils.proxies import wrap_asgi_with_proxy_headers

type Scope = MutableMapping[str, Any]


async def _seen_client(trusted: list[str], peer: str, forwarded: str) -> str:
    seen: list[str] = []

    async def app(scope: Scope, receive: object, send: object) -> None:
        seen.append(scope["client"][0])

    wrapped: Callable[..., Awaitable[None]] = wrap_asgi_with_proxy_headers(
        app, trusted_hosts=trusted
    )
    scope: Scope = {
        "type": "http",
        "client": (peer, 5000),
        "headers": [(b"x-forwarded-for", forwarded.encode())],
    }
    await wrapped(scope, None, None)
    return seen[0]


async def test_untrusted_peer_cannot_spoof_its_address() -> None:
    """A peer outside the trusted list keeps its socket address."""
    assert (
        await _seen_client(["127.0.0.1"], "203.0.113.9", "198.51.100.1")
        == "203.0.113.9"
    )


async def test_trusted_proxy_forwards_the_real_client() -> None:
    """A trusted proxy's X-Forwarded-For becomes the client address."""
    assert (
        await _seen_client(["10.0.0.0/8"], "10.1.2.3", "198.51.100.1") == "198.51.100.1"
    )
