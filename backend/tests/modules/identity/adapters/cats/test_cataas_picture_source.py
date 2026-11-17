import pytest

from app.modules.identity.adapters.cats.cataas_picture_source import CataasPictureSource
from app.modules.identity.adapters.cats.disabled_cat_picture_source import (
    DisabledCatPictureSource,
)
from app.modules.identity.adapters.cats.in_memory_cat_picture_source import (
    InMemoryCatPictureSource,
)
from app.modules.identity.domain.avatar import MAX_AVATAR_BYTES
from app.modules.identity.domain.errors import CatServiceUnavailableError
from app.shared_kernel.outbound_http import (
    InMemoryOutboundHttp,
    OutboundFailure,
    OutboundHttpError,
    OutboundResponse,
)

BASE = "https://cataas.com"
SEED = "0123456789abcdef"
CAT_URL = f"{BASE}/avatar/{SEED}"


def _reply(
    *,
    status: int = 200,
    content_type: str = "image/jpeg",
    body: bytes = b"\xff\xd8cat",
    url: str = CAT_URL,
) -> OutboundResponse:
    return OutboundResponse(
        url=url, status=status, headers={"content-type": content_type}, body=body
    )


def _source(reply: OutboundResponse | OutboundHttpError) -> CataasPictureSource:
    http = InMemoryOutboundHttp()
    http.reply(CAT_URL, reply)
    return CataasPictureSource(http, BASE, seed=lambda: SEED)


async def test_returns_image_body() -> None:
    """A square cat comes back as the reply's bytes."""
    assert await _source(_reply()).fetch() == b"\xff\xd8cat"


async def test_requests_an_avatar_with_size_cap() -> None:
    """The request asks for a cat avatar, caps the size and trusts the admin's URL."""
    http = InMemoryOutboundHttp()
    http.reply(CAT_URL, _reply())
    await CataasPictureSource(http, f"{BASE}/", seed=lambda: SEED).fetch()

    (request,) = http.requests
    assert request.url == CAT_URL
    assert request.params == {}
    assert request.headers["Accept"] == "image/*"
    assert request.max_bytes == MAX_AVATAR_BYTES
    assert request.admin_configured is True


async def test_each_press_uses_a_fresh_random_seed() -> None:
    """Without a seed given, every fetch asks for a different, random avatar."""
    http = InMemoryOutboundHttp()
    source = CataasPictureSource(http, BASE)
    for _ in range(2):
        with pytest.raises(CatServiceUnavailableError):
            await source.fetch()
    first, second = (request.url for request in http.requests)
    assert first != second
    assert first.startswith(f"{BASE}/avatar/")
    assert len(first.rsplit("/", 1)[1]) == 16


async def test_non_image_reply_is_unavailable() -> None:
    """An HTML error page is not a cat."""
    with pytest.raises(CatServiceUnavailableError):
        await _source(_reply(content_type="text/html", body=b"<html>")).fetch()


async def test_error_status_is_unavailable() -> None:
    """A server error from the service counts as unavailable."""
    with pytest.raises(CatServiceUnavailableError):
        await _source(_reply(status=500)).fetch()


async def test_empty_body_is_unavailable() -> None:
    """An image reply with nothing in it counts as unavailable."""
    with pytest.raises(CatServiceUnavailableError):
        await _source(_reply(body=b"")).fetch()


async def test_redirect_off_host_is_unavailable() -> None:
    """A reply that ended up on another host is not trusted."""
    with pytest.raises(CatServiceUnavailableError):
        await _source(_reply(url="https://elsewhere.example/cat.jpg")).fetch()


@pytest.mark.parametrize("failure", list(OutboundFailure))
async def test_outbound_failure_is_unavailable(failure: OutboundFailure) -> None:
    """Timeouts, refusals and oversize replies all count as unavailable."""
    with pytest.raises(CatServiceUnavailableError):
        await _source(OutboundHttpError(failure)).fetch()


async def test_disabled_source_always_unavailable() -> None:
    """With the service switched off, no request is attempted."""
    with pytest.raises(CatServiceUnavailableError):
        await DisabledCatPictureSource().fetch()


async def test_in_memory_source_serves_cats_then_fails_when_empty() -> None:
    """The test double hands out queued cats in order, then is unavailable."""
    source = InMemoryCatPictureSource([b"one", b"two"])
    assert await source.fetch() == b"one"
    assert await source.fetch() == b"two"
    with pytest.raises(CatServiceUnavailableError):
        await source.fetch()
