from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.http.public_origin_observer import PublicOriginObserver
from app.platform import proxy_signals
from app.platform.proxy_signals import ProxySignal

if TYPE_CHECKING:
    from starlette.types import Receive, Scope, Send

PUBLIC = "https://menagerist.example.com"


@pytest.fixture(autouse=True)
def _clean() -> None:
    proxy_signals.reset()


async def _visit(
    public: str,
    *,
    scheme: str,
    host: str,
    path: str = "/api/v1/node",
    scope_type: str = "http",
) -> list[Scope]:
    seen: list[Scope] = []

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        seen.append(scope)

    scope = {
        "type": scope_type,
        "scheme": scheme,
        "path": path,
        "headers": [(b"host", host.encode())],
    }
    await PublicOriginObserver(inner, public_origin=public)(scope, None, None)  # type: ignore[arg-type]
    return seen


def _counts() -> dict[ProxySignal, int]:
    return proxy_signals.counts()


async def test_the_public_address_raises_nothing() -> None:
    """Requests at the configured address are normal."""
    seen = await _visit(PUBLIC, scheme="https", host="menagerist.example.com")

    assert len(seen) == 1
    assert not any(_counts().values())


async def test_the_default_port_and_capitals_are_not_a_difference() -> None:
    """The comparison uses the same browser form as the setting."""
    await _visit(PUBLIC, scheme="https", host="Menagerist.Example.com:443")

    assert not any(_counts().values())


async def test_another_host_is_a_mismatch() -> None:
    """Reaching the app by its LAN address while the public one is set is flagged."""
    await _visit(PUBLIC, scheme="https", host="192.168.1.20")

    assert _counts()[ProxySignal.PUBLIC_ORIGIN_MISMATCH] == 1
    assert _counts()[ProxySignal.INSECURE_ORIGIN] == 0


async def test_plain_http_for_an_https_address_is_insecure() -> None:
    """The password and cookie would travel unencrypted, or the proxy hides HTTPS."""
    await _visit(PUBLIC, scheme="http", host="menagerist.example.com")

    assert _counts()[ProxySignal.INSECURE_ORIGIN] == 1
    assert _counts()[ProxySignal.PUBLIC_ORIGIN_MISMATCH] == 0


async def test_an_http_public_address_never_counts_as_insecure() -> None:
    """If the operator chose HTTP, plain HTTP is what they asked for."""
    await _visit("http://localhost:8080", scheme="http", host="127.0.0.1:8080")

    assert _counts()[ProxySignal.INSECURE_ORIGIN] == 0
    assert _counts()[ProxySignal.PUBLIC_ORIGIN_MISMATCH] == 1


async def test_health_probes_are_ignored() -> None:
    """The container's own health check calls localhost and must not warn."""
    await _visit(PUBLIC, scheme="http", host="localhost:8080", path="/api/health/ready")

    assert not any(_counts().values())


async def test_websocket_and_lifespan_scopes_are_ignored() -> None:
    """Only HTTP requests are compared."""
    seen = await _visit(
        PUBLIC, scheme="http", host="other.example", scope_type="lifespan"
    )

    assert len(seen) == 1
    assert not any(_counts().values())
