import asyncio
from typing import TYPE_CHECKING, Any

import httpx2
import pytest
from structlog.testing import capture_logs

from app.platform.config.outbound_http import OutboundHttpSettings
from app.platform.outbound_http import HttpxOutboundHttp, refusal_rule
from app.shared_kernel.outbound_http import OutboundFailure, OutboundHttpError

if TYPE_CHECKING:
    from collections.abc import MutableMapping

PUBLIC = "93.184.216.34"
SECOND = "93.184.216.35"


def client(
    transport: httpx2.AsyncBaseTransport,
    *,
    resolves: dict[str, list[str]] | None = None,
    total_timeout_seconds: float = 30.0,
) -> HttpxOutboundHttp:
    """A client over `transport` with a fake name service."""
    table = resolves or {}

    async def resolver(host: str, port: int) -> list[str]:
        """Resolver."""
        return table.get(host, [PUBLIC])

    return HttpxOutboundHttp(
        OutboundHttpSettings(total_timeout_seconds=total_timeout_seconds),
        version="1.2.3",
        resolver=resolver,
        transport=transport,
    )


def warnings(logs: list[MutableMapping[str, Any]]) -> list[MutableMapping[str, Any]]:
    """Only the warning-level events, leaving the debug trail aside."""
    return [log for log in logs if log["log_level"] == "warning"]


class Trickle(httpx2.AsyncByteStream):
    """A body that keeps sending a byte at a time, always inside the read timeout."""

    async def __aiter__(self):  # type: ignore[no-untyped-def]  # noqa: ANN204
        """Yield forever."""
        while True:
            await asyncio.sleep(0.01)
            yield b"x"


async def test_a_reply_that_trickles_is_cut_off_by_the_total_deadline() -> None:
    """The deadline covers the whole request, not just each read."""
    transport = httpx2.MockTransport(lambda r: httpx2.Response(200, stream=Trickle()))
    outbound = client(transport, total_timeout_seconds=0.1)

    with capture_logs() as logs, pytest.raises(OutboundHttpError) as caught:
        await outbound.get("https://example.com/")

    assert caught.value.failure is OutboundFailure.TIMEOUT
    assert warnings(logs) == [
        {
            "event": "outbound_request_failed",
            "host": "example.com",
            "failure": "timeout",
            "log_level": "warning",
        }
    ]


async def test_the_deadline_is_shared_by_every_redirect_hop() -> None:
    """Redirect hops draw on one budget."""

    async def slow(request: httpx2.Request) -> httpx2.Response:
        """Take a while, then redirect again."""
        await asyncio.sleep(0.06)
        return httpx2.Response(302, headers={"location": "https://example.com/next"})

    outbound = client(httpx2.MockTransport(slow), total_timeout_seconds=0.15)

    with pytest.raises(OutboundHttpError) as caught:
        await outbound.get("https://example.com/")

    assert caught.value.failure is OutboundFailure.TIMEOUT


async def test_a_refused_address_is_logged_with_host_address_and_rule() -> None:
    """A refusal names the host, the address and the rule, never the query."""
    outbound = client(
        httpx2.MockTransport(lambda r: httpx2.Response(200)),
        resolves={"intranet.example": ["10.0.0.8"]},
    )

    with capture_logs() as logs, pytest.raises(OutboundHttpError):
        await outbound.get("https://intranet.example/path?token=secret")

    assert warnings(logs) == [
        {
            "event": "outbound_request_refused",
            "host": "intranet.example",
            "address": "10.0.0.8",
            "rule": "private",
            "log_level": "warning",
        }
    ]


async def test_a_failed_request_is_logged_without_its_query_string() -> None:
    """A transport failure is logged at warning level with the host only."""

    def broken(request: httpx2.Request) -> httpx2.Response:
        """Fail like a dropped connection."""
        message = "boom"
        raise httpx2.ReadError(message)

    outbound = client(httpx2.MockTransport(broken))

    with capture_logs() as logs, pytest.raises(OutboundHttpError):
        await outbound.get("https://example.com/a?key=secret")

    assert warnings(logs) == [
        {
            "event": "outbound_request_failed",
            "host": "example.com",
            "failure": "network",
            "log_level": "warning",
        }
    ]
    assert "secret" not in str(logs)


async def test_a_later_address_is_tried_when_the_first_cannot_be_reached() -> None:
    """A host whose first record is unreachable still works through the next."""
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Refuse the first address, accept the second."""
        seen.append(request.url.host)
        if request.url.host == PUBLIC:
            message = "unreachable"
            raise httpx2.ConnectError(message)
        return httpx2.Response(200, content=b"ok")

    outbound = client(
        httpx2.MockTransport(handler), resolves={"example.com": [PUBLIC, SECOND]}
    )

    with capture_logs() as logs:
        response = await outbound.get("https://example.com/")

    assert response.body == b"ok"
    assert seen == [PUBLIC, SECOND]
    assert warnings(logs) == [
        {
            "event": "outbound_address_unreachable",
            "host": "example.com",
            "address": PUBLIC,
            "log_level": "warning",
        }
    ]


@pytest.mark.parametrize(
    ("error", "failure"),
    [
        (httpx2.ConnectError("x"), OutboundFailure.NETWORK),
        (httpx2.ConnectTimeout("x"), OutboundFailure.TIMEOUT),
    ],
)
async def test_every_address_unreachable_is_a_fixed_failure(
    error: httpx2.HTTPError, failure: OutboundFailure
) -> None:
    """When no address works the last error decides the failure."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Never connect."""
        raise error

    outbound = client(
        httpx2.MockTransport(handler), resolves={"example.com": [PUBLIC, SECOND]}
    )

    with pytest.raises(OutboundHttpError) as caught:
        await outbound.get("https://example.com/")

    assert caught.value.failure is failure


async def test_a_read_error_does_not_try_another_address() -> None:
    """Only failing to connect moves on to the next address."""
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Connect, then fail mid-reply."""
        seen.append(request.url.host)
        message = "reset"
        raise httpx2.ReadError(message)

    outbound = client(
        httpx2.MockTransport(handler), resolves={"example.com": [PUBLIC, SECOND]}
    )

    with pytest.raises(OutboundHttpError):
        await outbound.get("https://example.com/")

    assert seen == [PUBLIC]


async def test_a_read_timeout_is_a_timeout_failure() -> None:
    """A per-read timeout is reported as a timeout."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Stall."""
        message = "slow"
        raise httpx2.ReadTimeout(message)

    outbound = client(httpx2.MockTransport(handler))

    with pytest.raises(OutboundHttpError) as caught:
        await outbound.get("https://example.com/")

    assert caught.value.failure is OutboundFailure.TIMEOUT


@pytest.mark.parametrize(
    ("address", "rule"),
    [
        ("127.0.0.1", "loopback"),
        ("::1", "loopback"),
        ("169.254.169.254", "link_local"),
        ("224.0.0.1", "multicast"),
        ("10.0.0.5", "private"),
        ("0.0.0.0", "unspecified"),
        ("64:ff9b::7f00:1", "embeds_ipv4"),
        ("100.64.0.1", "not_global"),
        ("::ffff:10.0.0.1", "private"),
        ("not an address", "not_an_address"),
        (PUBLIC, "public"),
    ],
)
def test_refusal_rule_names_why_an_address_is_not_public(
    address: str, rule: str
) -> None:
    """The log names the rule that refused an address."""
    assert refusal_rule(address) == rule


async def test_each_hop_and_redirect_is_logged_at_debug_without_path_or_query() -> None:
    """Debug logs show the route taken but never the path, query or credentials."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Redirect once, then answer."""
        if request.url.path == "/start":
            return httpx2.Response(
                302, headers={"location": "https://other.example/final?t=secret"}
            )
        return httpx2.Response(200)

    outbound = client(httpx2.MockTransport(handler))

    with capture_logs() as logs:
        await outbound.get("https://example.com/start?key=secret")

    assert [(log["event"], log["log_level"]) for log in logs] == [
        ("outbound_hop_started", "debug"),
        ("outbound_hop_completed", "debug"),
        ("outbound_redirect_followed", "debug"),
        ("outbound_hop_started", "debug"),
        ("outbound_hop_completed", "debug"),
    ]
    assert logs[0]["addresses"] == [PUBLIC]
    assert logs[0]["via_proxy"] is False
    assert logs[2]["from_host"] == "example.com"
    assert logs[2]["to_host"] == "other.example"
    assert "secret" not in str(logs)
    assert "/start" not in str(logs)
