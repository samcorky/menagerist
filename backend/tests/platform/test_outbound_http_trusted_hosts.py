import httpx2
import pytest
from structlog.testing import capture_logs

from app.platform.config.outbound_http import OutboundHttpSettings
from app.platform.outbound_http import HttpxOutboundHttp, is_trusted_private_address
from app.shared_kernel.outbound_http import (
    InMemoryOutboundHttp,
    OutboundFailure,
    OutboundHttpError,
    OutboundResponse,
)

PUBLIC = "93.184.216.34"


def client(
    trusted_hosts: str,
    resolves: dict[str, list[str]],
    *,
    handler: httpx2.MockTransport | None = None,
) -> HttpxOutboundHttp:
    """A client trusting `trusted_hosts`, with a fake name service."""

    async def resolver(host: str, port: int) -> list[str]:
        """Resolver."""
        return resolves.get(host, [PUBLIC])

    return HttpxOutboundHttp(
        OutboundHttpSettings(trusted_hosts=trusted_hosts),
        version="1.2.3",
        resolver=resolver,
        transport=handler
        or httpx2.MockTransport(lambda r: httpx2.Response(200, content=b"ok")),
    )


async def failure_of(call: object) -> OutboundFailure:
    """The failure an awaited call raised."""
    with pytest.raises(OutboundHttpError) as caught:
        await call  # type: ignore[misc]
    return caught.value.failure


async def test_a_trusted_host_may_resolve_privately_for_an_admin_configured_call() -> (
    None
):
    """The allowance works, connects to the checked address and is logged."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Record the request."""
        seen.append(request)
        return httpx2.Response(200, content=b"lan")

    outbound = client(
        "ollama", {"ollama": ["172.18.0.5"]}, handler=httpx2.MockTransport(handler)
    )

    with capture_logs() as logs:
        response = await outbound.get("http://ollama:11434/api", admin_configured=True)

    assert response.body == b"lan"
    assert seen[0].url.host == "172.18.0.5"
    assert seen[0].headers["host"] == "ollama:11434"
    assert {
        "event": "outbound_trusted_host_used",
        "host": "ollama",
        "addresses": ["172.18.0.5"],
        "log_level": "warning",
    } in logs


async def test_a_trusted_host_is_refused_when_the_caller_is_not_admin_configured() -> (
    None
):
    """A URL a person typed never gets the allowance."""
    outbound = client("ollama", {"ollama": ["10.0.0.5"]})

    assert (
        await failure_of(outbound.get("http://ollama/"))
        is OutboundFailure.BLOCKED_ADDRESS
    )


async def test_an_unlisted_host_is_refused_even_when_admin_configured() -> None:
    """Only listed names are trusted."""
    outbound = client("ollama", {"other": ["10.0.0.5"]})

    assert (
        await failure_of(outbound.get("http://other/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )


async def test_a_subdomain_of_a_trusted_name_inherits_nothing() -> None:
    """Matching is exact: no suffix or wildcard trust."""
    outbound = client("books.lan", {"evil.books.lan": ["10.0.0.5"]})

    assert (
        await failure_of(outbound.get("http://evil.books.lan/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )


async def test_every_address_must_be_allowed_not_just_the_first() -> None:
    """One bad record refuses the whole name."""
    outbound = client("ollama", {"ollama": ["10.0.0.5", "127.0.0.1"]})

    assert (
        await failure_of(outbound.get("http://ollama/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "::1", "169.254.169.254", "fe80::1", "224.0.0.1", "0.0.0.0"],
)
async def test_the_deny_floor_holds_for_a_trusted_host(address: str) -> None:
    """Loopback, link-local, multicast and unspecified are refused regardless."""
    outbound = client("ollama", {"ollama": [address]})

    assert (
        await failure_of(outbound.get("http://ollama/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )


async def test_a_port_entry_trusts_only_that_port() -> None:
    """`host:port` matches that port alone; a bare host matches any."""
    resolves = {"books.lan": ["192.168.1.9"]}
    outbound = client("books.lan:8080", resolves)

    assert (await outbound.get("http://books.lan:8080/", admin_configured=True)).body
    assert (
        await failure_of(outbound.get("http://books.lan:9000/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )
    assert (
        await client("books.lan", resolves).get(
            "http://books.lan:9000/", admin_configured=True
        )
    ).body


async def test_an_ip_literal_is_never_trusted_by_name() -> None:
    """Trust is for names; an address in the URL is refused."""
    outbound = client("ollama", {})

    assert (
        await failure_of(outbound.get("http://10.0.0.5/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )


async def test_a_redirect_off_the_trusted_host_is_judged_afresh() -> None:
    """The allowance does not follow a redirect to another private host."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Redirect to an unlisted host."""
        return httpx2.Response(302, headers={"location": "http://other/"})

    outbound = client(
        "ollama",
        {"ollama": ["10.0.0.5"], "other": ["10.0.0.6"]},
        handler=httpx2.MockTransport(handler),
    )

    assert (
        await failure_of(outbound.get("http://ollama/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )


async def test_a_public_configured_host_cannot_redirect_onto_a_trusted_one() -> None:
    """A third-party service cannot steer a request onto the trusted network."""
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Redirect from the public provider to the trusted LAN host."""
        seen.append(request.headers["host"])
        return httpx2.Response(302, headers={"location": "https://ollama/api"})

    outbound = client(
        "ollama",
        {"ollama": ["10.0.0.5"]},
        handler=httpx2.MockTransport(handler),
    )

    assert (
        await failure_of(outbound.get("https://example.com/", admin_configured=True))
        is OutboundFailure.BLOCKED_ADDRESS
    )
    assert seen == ["example.com"]


async def test_a_trusted_host_may_redirect_within_itself() -> None:
    """The allowance still holds for further paths on the configured host."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Redirect once on the same host, then answer."""
        if request.url.path == "/old":
            return httpx2.Response(302, headers={"location": "/new"})
        return httpx2.Response(200, content=b"moved")

    outbound = client(
        "ollama", {"ollama": ["10.0.0.5"]}, handler=httpx2.MockTransport(handler)
    )

    response = await outbound.get("http://ollama/old", admin_configured=True)

    assert response.body == b"moved"


async def test_a_trusted_name_that_resolves_publicly_is_not_logged_as_used() -> None:
    """The log only records requests that really used the allowance."""
    outbound = client("example.com", {})

    with capture_logs() as logs:
        await outbound.get("https://example.com/", admin_configured=True)

    assert not [log for log in logs if log["event"] == "outbound_trusted_host_used"]


@pytest.mark.parametrize(
    ("address", "trustable"),
    [
        ("10.1.2.3", True),
        ("172.16.0.1", True),
        ("192.168.0.1", True),
        ("fd00::1", True),
        ("::ffff:10.0.0.1", True),
        ("100.64.0.1", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),
        (PUBLIC, False),
        ("garbage", False),
    ],
)
def test_only_rfc_1918_and_unique_local_ranges_are_trustable(
    address: str, trustable: bool
) -> None:
    """The trust applies to a fixed set of private ranges."""
    assert is_trusted_private_address(address) is trustable


@pytest.mark.parametrize(
    "value", ["*.lan", "http://ollama", "ollama/path", "10.0.0.5", "a b", "x:99999x"]
)
def test_trusted_hosts_must_be_exact_names(value: str) -> None:
    """Wildcards, schemes, paths and addresses are refused at start-up."""
    with pytest.raises(ValueError, match="exact host name"):
        OutboundHttpSettings(trusted_hosts=value)


def test_trusted_hosts_are_normalised_and_empty_trusts_nothing() -> None:
    """Entries are lower-cased and trimmed; the default is empty."""
    assert OutboundHttpSettings().trusted_host_entries == frozenset()
    settings = OutboundHttpSettings(trusted_hosts=" Ollama , books.lan:8080,,")
    assert settings.trusted_host_entries == {"ollama", "books.lan:8080"}


async def test_the_in_memory_client_records_who_configured_the_destination() -> None:
    """Tests of callers can assert they flagged a destination as admin-configured."""
    memory = InMemoryOutboundHttp()
    memory.reply("http://ollama/", OutboundResponse(url="http://ollama/", status=200))

    await memory.get("http://ollama/", admin_configured=True)

    assert memory.requests[0].admin_configured is True
