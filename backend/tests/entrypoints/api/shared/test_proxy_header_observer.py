from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.proxy_header_observer import ProxyHeaderObserver
from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send


@pytest.fixture(autouse=True)
def _clean() -> None:
    proxy_signals.reset()


async def _run(
    trusted: list[str],
    *,
    client: tuple[str, int] | None,
    headers: list[tuple[bytes, bytes]],
    scope_type: str = "http",
) -> list[Scope]:
    seen: list[Scope] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    scope = {"type": scope_type, "client": client, "headers": headers}
    await ProxyHeaderObserver(inner, trusted=trusted)(scope, None, None)  # type: ignore[arg-type]
    return seen


def _noted() -> int:
    return proxy_signals.counts()[ProxySignal.UNTRUSTED_FORWARDING]


FORWARDED = [(b"x-forwarded-for", b"203.0.113.9")]


@pytest.mark.parametrize(
    ("trusted", "client", "headers", "noted"),
    [
        (["127.0.0.1"], ("172.21.0.10", 1), FORWARDED, 1),
        (["127.0.0.1"], ("172.21.0.10", 1), [(b"x-forwarded-proto", b"https")], 1),
        (["127.0.0.1"], ("127.0.0.1", 1), FORWARDED, 0),
        (["172.21.0.0/16"], ("172.21.0.10", 1), FORWARDED, 0),
        (["172.21.0.0/16"], ("172.22.0.10", 1), FORWARDED, 1),
        (["*"], ("172.21.0.10", 1), FORWARDED, 0),
        (["proxy.internal"], ("proxy.internal", 1), FORWARDED, 0),
        (["127.0.0.1"], None, FORWARDED, 1),
        (["127.0.0.1"], ("172.21.0.10", 1), [(b"host", b"x")], 0),
    ],
)
async def test_notes_forwarding_headers_from_an_untrusted_peer(
    trusted: list[str],
    client: tuple[str, int] | None,
    headers: list[tuple[bytes, bytes]],
    noted: int,
) -> None:
    """Only forwarding headers from a peer outside the trusted list are noted."""
    seen = await _run(trusted, client=client, headers=headers)

    assert len(seen) == 1  # always passed on, never changed
    assert _noted() == noted


async def test_ignores_lifespan_and_websocket_scopes() -> None:
    """Only HTTP requests are looked at."""
    await _run(
        ["127.0.0.1"], client=("1.2.3.4", 1), headers=FORWARDED, scope_type="lifespan"
    )

    assert _noted() == 0
