import httpx2
import pytest
from pydantic import ValidationError

from app.platform.config.outbound_http import OutboundHttpSettings
from app.platform.outbound_http import HttpxOutboundHttp, bypasses_proxy
from app.shared_kernel.outbound_http import OutboundFailure, OutboundHttpError

PUBLIC = "93.184.216.34"
PROXY = "http://user:secret@proxy.internal:3128"


class Recorder:
    """Stands in for the proxy transport and notes which proxies were used."""

    def __init__(self) -> None:
        self.proxies: list[str] = []
        self.requests: list[httpx2.Request] = []

    def transport(self, proxy: str) -> httpx2.AsyncBaseTransport:
        """Build a transport for `proxy`, recording the request it later serves."""
        self.proxies.append(proxy)

        def handler(request: httpx2.Request) -> httpx2.Response:
            """Handler."""
            self.requests.append(request)
            return httpx2.Response(200, content=b"via proxy")

        return httpx2.MockTransport(handler)


def client(
    monkeypatch: pytest.MonkeyPatch,
    recorder: Recorder,
    *,
    env: dict[str, str],
    resolves: dict[str, list[str] | None] | None = None,
) -> tuple[HttpxOutboundHttp, list[httpx2.Request]]:
    """A client reading `env` as its settings, with a direct mock transport."""
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    table = resolves or {}
    direct: list[httpx2.Request] = []

    async def resolver(host: str, port: int) -> list[str]:
        """Resolver."""
        found = table.get(host, [PUBLIC])
        if found is None:
            raise OutboundHttpError(OutboundFailure.NETWORK)
        return found

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        direct.append(request)
        return httpx2.Response(200, content=b"direct")

    outbound = HttpxOutboundHttp(
        OutboundHttpSettings(),
        version="1.2.3",
        resolver=resolver,
        transport=httpx2.MockTransport(handler),
        proxy_transport=recorder.transport,
    )
    return outbound, direct


async def test_an_https_request_goes_through_the_https_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An https request goes through the https proxy."""
    recorder = Recorder()
    outbound, direct = client(monkeypatch, recorder, env={"HTTPS_PROXY": PROXY})

    response = await outbound.get("https://example.com/a", params={"p": 1})

    assert response.body == b"via proxy"
    assert recorder.proxies == [PROXY]
    assert not direct
    (request,) = recorder.requests
    assert request.url.host == "example.com"
    assert str(request.url) == "https://example.com/a?p=1"
    assert request.headers["user-agent"].startswith("Menagerist/1.2.3 (")


async def test_an_http_request_uses_the_http_proxy_and_lower_case_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An http request uses the http proxy, and lower-case names work."""
    recorder = Recorder()
    outbound, _ = client(monkeypatch, recorder, env={"http_proxy": PROXY})

    await outbound.get("http://example.com/")

    assert recorder.proxies == [PROXY]


async def test_a_scheme_with_no_proxy_of_its_own_goes_direct(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A scheme with no proxy of its own goes direct, pinned to its address."""
    recorder = Recorder()
    outbound, direct = client(monkeypatch, recorder, env={"HTTP_PROXY": PROXY})

    response = await outbound.get("https://example.com/")

    assert response.body == b"direct"
    assert not recorder.proxies
    assert direct[0].url.host == PUBLIC


async def test_a_host_in_no_proxy_goes_direct(monkeypatch: pytest.MonkeyPatch) -> None:
    """A host in NO_PROXY goes direct, pinned to its address."""
    recorder = Recorder()
    outbound, direct = client(
        monkeypatch,
        recorder,
        env={"HTTPS_PROXY": PROXY, "NO_PROXY": "other.example, .example.com"},
    )

    response = await outbound.get("https://api.example.com/")

    assert response.body == b"direct"
    assert not recorder.proxies
    assert direct[0].url.host == PUBLIC


@pytest.mark.parametrize(
    "url", ["https://internal.example/", "https://10.0.0.5/", "https://[::1]/"]
)
async def test_a_target_that_is_private_here_is_refused_before_the_proxy(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    """A target that is private here is refused before the proxy is used."""
    recorder = Recorder()
    outbound, _ = client(
        monkeypatch,
        recorder,
        env={"HTTPS_PROXY": PROXY},
        resolves={"internal.example": [PUBLIC, "10.0.0.8"]},
    )

    with pytest.raises(OutboundHttpError) as caught:
        await outbound.get(url)

    assert caught.value.failure is OutboundFailure.BLOCKED_ADDRESS
    assert not recorder.proxies


async def test_a_name_this_host_cannot_resolve_is_left_to_the_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name this host cannot resolve is left to the proxy."""
    recorder = Recorder()
    outbound, _ = client(
        monkeypatch,
        recorder,
        env={"HTTPS_PROXY": PROXY},
        resolves={"proxy-only.example": None},
    )

    response = await outbound.get("https://proxy-only.example/")

    assert response.body == b"via proxy"


async def test_a_redirect_is_checked_and_proxied_like_the_first_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A redirect is checked and proxied like the first request."""
    recorder = Recorder()

    def transport(proxy: str) -> httpx2.AsyncBaseTransport:
        """Redirect once, to a host that resolves privately."""
        recorder.proxies.append(proxy)
        return httpx2.MockTransport(
            lambda r: httpx2.Response(
                302, headers={"location": "https://internal.example/"}
            )
        )

    outbound, _ = client(
        monkeypatch,
        recorder,
        env={"HTTPS_PROXY": PROXY},
        resolves={"internal.example": ["10.0.0.8"]},
    )
    outbound._proxy_transport = transport

    with pytest.raises(OutboundHttpError) as caught:
        await outbound.get("https://example.com/")

    assert caught.value.failure is OutboundFailure.BLOCKED_ADDRESS
    assert recorder.proxies == [PROXY]


async def test_the_proxy_url_and_its_password_are_never_in_an_error() -> None:
    """The proxy URL and its password are never in an error."""

    def broken(proxy: str) -> httpx2.AsyncBaseTransport:
        """Fail the way an unreachable proxy does."""

        def handler(request: httpx2.Request) -> httpx2.Response:
            """Handler."""
            raise httpx2.ConnectError(f"cannot reach {proxy}")

        return httpx2.MockTransport(handler)

    async def resolver(host: str, port: int) -> list[str]:
        """Resolver."""
        return [PUBLIC]

    settings = OutboundHttpSettings(HTTPS_PROXY=PROXY)
    outbound = HttpxOutboundHttp(
        settings, version="1", resolver=resolver, proxy_transport=broken
    )

    with pytest.raises(OutboundHttpError) as caught:
        await outbound.get("https://example.com/")

    assert caught.value.failure is OutboundFailure.NETWORK
    assert "secret" not in str(caught.value)
    assert "secret" not in repr(settings)


@pytest.mark.parametrize(
    ("host", "no_proxy", "bypassed"),
    [
        ("example.com", "", False),
        ("example.com", "example.com", True),
        ("api.example.com", "example.com", True),
        ("api.example.com", ".example.com", True),
        ("notexample.com", "example.com", False),
        ("Example.COM", "EXAMPLE.com", True),
        ("example.com", "other.example, example.com", True),
        ("example.com", "*", True),
        ("example.com", " , ,", False),
        ("10.1.2.3", "10.0.0.0/8", True),
        ("11.1.2.3", "10.0.0.0/8", False),
        ("10.1.2.3", "10.1.2.3", True),
        ("::1", "::1", True),
        ("::1", "[::1]", False),
        ("example.com", "10.0.0.0/8", False),
        ("10.1.2.3", "not a network", False),
    ],
)
def test_no_proxy_matching(host: str, no_proxy: str, bypassed: bool) -> None:
    """NO_PROXY matches names, domains, addresses and ranges."""
    assert bypasses_proxy(host, no_proxy) is bypassed


def test_the_default_proxy_transport_is_a_real_http_transport() -> None:
    """The default proxy transport is a real http transport."""
    from app.platform.outbound_http import _proxy_transport

    assert isinstance(_proxy_transport("http://proxy:3128"), httpx2.AsyncHTTPTransport)


def test_the_proxy_settings_read_the_standard_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The proxy settings read the standard names, upper or lower case."""
    monkeypatch.setenv("HTTP_PROXY", f" {PROXY} ")
    monkeypatch.setenv("https_proxy", "https://proxy.example")
    monkeypatch.setenv("no_proxy", "localhost,.internal")

    settings = OutboundHttpSettings()

    assert settings.http_proxy is not None
    assert settings.http_proxy.get_secret_value() == PROXY
    assert settings.https_proxy is not None
    assert settings.https_proxy.get_secret_value() == "https://proxy.example"
    assert settings.no_proxy == "localhost,.internal"
    assert "secret" not in repr(settings)


def test_no_proxy_is_the_default() -> None:
    """No proxy is the default."""
    settings = OutboundHttpSettings()

    assert (settings.http_proxy, settings.https_proxy, settings.no_proxy) == (
        None,
        None,
        "",
    )


def test_an_empty_proxy_means_none(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty proxy means none."""
    monkeypatch.setenv("HTTPS_PROXY", "  ")

    assert OutboundHttpSettings().https_proxy is None


@pytest.mark.parametrize(
    "value", ["ftp://proxy:21", "proxy:3128", "not a url", "http://", "http://h:abc"]
)
def test_a_proxy_that_is_not_a_web_address_is_refused(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """A proxy that is not a web address is refused."""
    monkeypatch.setenv("HTTP_PROXY", value)

    with pytest.raises(ValidationError):
        OutboundHttpSettings()
