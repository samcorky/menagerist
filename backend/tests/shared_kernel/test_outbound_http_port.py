import pytest

from app.shared_kernel.outbound_http import (
    InMemoryOutboundHttp,
    OutboundFailure,
    OutboundHttpError,
    OutboundResponse,
)

URL = "https://example.com/a"


async def test_a_registered_reply_is_served_and_the_request_recorded() -> None:
    """A registered reply is served and the request recorded."""
    http = InMemoryOutboundHttp()
    reply = OutboundResponse(url=URL, status=200, body=b"hi")
    http.reply(URL, reply)

    got = await http.get(URL, headers={"A": "1"}, params={"p": 2}, max_bytes=10)

    assert got is reply
    (request,) = http.requests
    assert (request.url, request.headers, request.params, request.max_bytes) == (
        URL,
        {"A": "1"},
        {"p": 2},
        10,
    )


async def test_an_unregistered_url_is_unreachable() -> None:
    """An unregistered URL is unreachable."""
    with pytest.raises(OutboundHttpError) as caught:
        await InMemoryOutboundHttp().get(URL)

    assert caught.value.failure is OutboundFailure.NETWORK


async def test_a_registered_error_is_raised() -> None:
    """A registered error is raised."""
    http = InMemoryOutboundHttp()
    http.reply(URL, OutboundHttpError(OutboundFailure.TIMEOUT))

    with pytest.raises(OutboundHttpError) as caught:
        await http.get(URL)

    assert caught.value.failure is OutboundFailure.TIMEOUT


async def test_a_body_over_the_requested_limit_is_too_large() -> None:
    """A body over the requested limit is too large."""
    http = InMemoryOutboundHttp()
    http.reply(URL, OutboundResponse(url=URL, status=200, body=b"12345"))

    with pytest.raises(OutboundHttpError) as caught:
        await http.get(URL, max_bytes=4)

    assert caught.value.failure is OutboundFailure.TOO_LARGE
    assert (await http.get(URL, max_bytes=5)).body == b"12345"
