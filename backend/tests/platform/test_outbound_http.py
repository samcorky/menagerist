import httpx2
import pytest

from app.platform.config.outbound_http import OutboundHttpSettings
from app.platform.outbound_http import (
    MAX_REDIRECTS,
    HttpxOutboundHttp,
    build_user_agent,
    is_public_address,
    resolve_host,
)
from app.shared_kernel.outbound_http import OutboundFailure, OutboundHttpError

PUBLIC = "93.184.216.34"
PROJECT = "https://github.com/samcorky/menagerist"


def client(
    handler: httpx2.MockTransport | None = None,
    *,
    resolves: dict[str, list[str]] | None = None,
    contact: str = "",
    max_response_bytes: int = 4096,
) -> HttpxOutboundHttp:
    """A client over a mock transport with a fake name service."""
    table = resolves or {}

    async def resolver(host: str, port: int) -> list[str]:
        """Resolver."""
        return table.get(host, [PUBLIC])

    return HttpxOutboundHttp(
        OutboundHttpSettings(contact=contact, max_response_bytes=max_response_bytes),
        version="1.2.3",
        resolver=resolver,
        transport=handler or httpx2.MockTransport(lambda r: httpx2.Response(200)),
    )


async def failure_of(call: object) -> OutboundFailure:
    """The failure an awaited call raised."""
    with pytest.raises(OutboundHttpError) as caught:
        await call  # type: ignore[misc]
    return caught.value.failure


@pytest.mark.parametrize(
    ("address", "public"),
    [
        (PUBLIC, True),
        (f"::ffff:{PUBLIC}", True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("127.0.0.1", False),
        ("10.0.0.5", False),
        ("172.16.0.1", False),
        ("192.168.1.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("240.0.0.1", False),
        ("::1", False),
        ("fe80::1%eth0", False),
        ("fc00::1", False),
        ("ff02::1", False),
        ("::ffff:127.0.0.1", False),
        ("::ffff:10.0.0.1", False),
        ("64:ff9b::7f00:1", False),
        ("2002:7f00:1::", False),
        ("not an address", False),
    ],
)
def test_only_public_addresses_are_allowed(address: str, public: bool) -> None:
    """Only public addresses are allowed."""
    assert is_public_address(address) is public


def test_the_user_agent_names_the_product_version_and_project() -> None:
    """The user agent names the product, version and project."""
    assert build_user_agent("1.2.3", "") == f"Menagerist/1.2.3 (+{PROJECT})"
    assert build_user_agent("1.2.3", "me@example.com") == (
        f"Menagerist/1.2.3 (+{PROJECT}; contact: me@example.com)"
    )


def test_the_client_exposes_its_user_agent() -> None:
    """The client exposes its user agent."""
    assert client().user_agent == f"Menagerist/1.2.3 (+{PROJECT})"


async def test_a_request_is_made_to_the_checked_address_with_the_real_host() -> None:
    """A request is made to the checked address with the real host."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        seen.append(request)
        return httpx2.Response(200, headers={"X-Thing": "1"}, content=b"hello")

    outbound = client(httpx2.MockTransport(handler), contact="me@example.com")
    response = await outbound.get(
        "https://api.example.com/v1/items",
        headers={"Accept": "application/json", "User-Agent": "spoof"},
        params={"page": 2},
    )

    (request,) = seen
    assert request.url.host == PUBLIC
    assert request.url.path == "/v1/items"
    assert request.url.params["page"] == "2"
    assert request.headers["host"] == "api.example.com"
    assert request.extensions["sni_hostname"] == "api.example.com"
    assert request.headers["accept"] == "application/json"
    assert request.headers["user-agent"] == (
        f"Menagerist/1.2.3 (+{PROJECT}; contact: me@example.com)"
    )
    assert (response.status, response.body) == (200, b"hello")
    assert response.url == "https://api.example.com/v1/items?page=2"
    assert response.headers["x-thing"] == "1"


async def test_a_non_default_port_stays_in_the_host_header() -> None:
    """A non-default port stays in the host header."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        seen.append(request)
        return httpx2.Response(200)

    await client(httpx2.MockTransport(handler)).get("http://example.com:8080/")

    assert seen[0].headers["host"] == "example.com:8080"
    assert seen[0].url.port == 8080


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/",
        "https://internal.example/",
    ],
)
async def test_a_url_that_reaches_a_private_address_is_refused(url: str) -> None:
    """A URL that reaches a private address is refused."""
    resolves = {"localhost": ["127.0.0.1"], "internal.example": [PUBLIC, "10.0.0.8"]}
    called: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        called.append(request)
        return httpx2.Response(200)

    outbound = client(httpx2.MockTransport(handler), resolves=resolves)

    assert await failure_of(outbound.get(url)) is OutboundFailure.BLOCKED_ADDRESS
    assert not called


@pytest.mark.parametrize(
    "url", ["ftp://example.com/", "file:///etc/passwd", "/path", "https:///no-host"]
)
async def test_only_http_and_https_are_allowed(url: str) -> None:
    """Only http and https are allowed."""
    assert await failure_of(client().get(url)) is OutboundFailure.INVALID_URL


async def test_a_malformed_url_is_refused() -> None:
    """A malformed URL is refused."""
    assert (
        await failure_of(client().get("http://host:abc/"))
        is OutboundFailure.INVALID_URL
    )


async def test_a_host_that_does_not_resolve_is_a_network_failure() -> None:
    """A host that does not resolve is a network failure."""
    outbound = client(resolves={"gone.example": []})

    failure = await failure_of(outbound.get("https://gone.example/"))

    assert failure is OutboundFailure.NETWORK


async def test_a_redirect_to_a_private_address_is_refused() -> None:
    """A redirect to a private address is refused."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        return httpx2.Response(302, headers={"location": "https://metadata.internal/"})

    outbound = client(
        httpx2.MockTransport(handler), resolves={"metadata.internal": ["10.0.0.1"]}
    )

    failure = await failure_of(outbound.get("https://example.com/"))

    assert failure is OutboundFailure.BLOCKED_ADDRESS


async def test_a_public_redirect_is_followed_and_reported() -> None:
    """A public redirect is followed and reported."""
    paths: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        paths.append(request.url.path)
        if request.url.path == "/":
            return httpx2.Response(301, headers={"location": "/moved?x=1"})
        return httpx2.Response(200, content=b"ok")

    response = await client(httpx2.MockTransport(handler)).get("https://example.com/")

    assert paths == ["/", "/moved"]
    assert response.url == "https://example.com/moved?x=1"


async def test_credentials_are_dropped_when_a_redirect_changes_host() -> None:
    """Credentials are dropped when a redirect changes host."""
    seen: list[httpx2.Headers] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        seen.append(request.headers)
        if len(seen) == 1:
            return httpx2.Response(302, headers={"location": "https://other.example/"})
        return httpx2.Response(200)

    await client(httpx2.MockTransport(handler)).get(
        "https://example.com/", headers={"Authorization": "Bearer secret"}
    )

    assert seen[0]["authorization"] == "Bearer secret"
    assert "authorization" not in seen[1]


@pytest.mark.parametrize(
    ("location", "failure"),
    [
        ("http://example.com/", OutboundFailure.INVALID_URL),
        ("//[bad/", OutboundFailure.INVALID_URL),
    ],
)
async def test_an_unsafe_redirect_target_is_refused(
    location: str, failure: OutboundFailure
) -> None:
    """An unsafe redirect target is refused."""
    transport = httpx2.MockTransport(
        lambda r: httpx2.Response(302, headers={"location": location})
    )

    assert await failure_of(client(transport).get("https://example.com/")) is failure


async def test_too_many_redirects_are_refused() -> None:
    """Too many redirects are refused."""
    count = 0

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        nonlocal count
        count += 1
        return httpx2.Response(302, headers={"location": "/again"})

    outbound = client(httpx2.MockTransport(handler))

    failure = await failure_of(outbound.get("https://a.example/"))

    assert failure is OutboundFailure.TOO_MANY_REDIRECTS
    assert count == MAX_REDIRECTS + 1


async def test_a_redirect_without_a_location_is_returned_as_it_is() -> None:
    """A redirect without a location is returned as it is."""
    transport = httpx2.MockTransport(lambda r: httpx2.Response(304))

    assert (await client(transport).get("https://example.com/")).status == 304


async def test_a_body_over_the_limit_is_refused_while_reading() -> None:
    """A body over the limit is refused while reading."""
    transport = httpx2.MockTransport(
        lambda r: httpx2.Response(200, content=b"x" * 5000)
    )

    failure = await failure_of(client(transport).get("https://example.com/"))

    assert failure is OutboundFailure.TOO_LARGE


async def test_a_declared_length_over_the_limit_is_refused_before_reading() -> None:
    """A declared length over the limit is refused before reading."""
    transport = httpx2.MockTransport(
        lambda r: httpx2.Response(200, headers={"content-length": "999999"})
    )

    failure = await failure_of(client(transport).get("https://example.com/"))

    assert failure is OutboundFailure.TOO_LARGE


async def test_a_caller_can_lower_the_limit_but_not_raise_it() -> None:
    """A caller can lower the limit but not raise it."""
    transport = httpx2.MockTransport(
        lambda r: httpx2.Response(200, content=b"x" * 2000)
    )
    outbound = client(transport, max_response_bytes=4096)

    lowered = await failure_of(outbound.get("https://example.com/", max_bytes=1000))
    raised = await outbound.get("https://example.com/", max_bytes=10**9)

    assert lowered is OutboundFailure.TOO_LARGE
    assert len(raised.body) == 2000


@pytest.mark.parametrize(
    ("raised", "failure"),
    [
        (httpx2.ReadTimeout("slow"), OutboundFailure.TIMEOUT),
        (httpx2.ConnectError("down"), OutboundFailure.NETWORK),
    ],
)
async def test_a_transport_error_is_a_fixed_failure(
    raised: Exception, failure: OutboundFailure
) -> None:
    """A transport error is a fixed failure."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        raise raised

    outbound = client(httpx2.MockTransport(handler))

    assert await failure_of(outbound.get("https://a.example/")) is failure


async def test_the_system_resolver_lists_each_address_once() -> None:
    """The system resolver lists each address once."""
    assert await resolve_host("127.0.0.1", 80) == ["127.0.0.1"]


async def test_the_system_resolver_reports_an_unknown_host_as_a_network_failure() -> (
    None
):
    """The system resolver reports an unknown host as a network failure."""
    failure = await failure_of(resolve_host("nonexistent.invalid", 443))

    assert failure is OutboundFailure.NETWORK
