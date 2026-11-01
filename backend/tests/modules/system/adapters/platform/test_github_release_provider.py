import httpx2
import pytest

from app.modules.system.adapters.platform.github_release_provider import (
    MAX_BODY_BYTES,
    GitHubReleaseProvider,
)
from app.modules.system.domain.release import (
    CheckFailure,
    ReleaseCheckError,
    RepositoryRef,
)

REPOSITORY = RepositoryRef(owner="samcorky", name="menagerist")


def provider(handler: httpx2.MockTransport) -> GitHubReleaseProvider:
    """Provider."""
    return GitHubReleaseProvider(user_agent="menagerist/test", transport=handler)


def serving(
    status: int = 200, body: object = None, **kwargs: object
) -> httpx2.MockTransport:
    """Serving."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        return httpx2.Response(status, json=body if body is not None else [], **kwargs)  # type: ignore[arg-type]

    return httpx2.MockTransport(handler)


async def test_releases_are_read_from_the_api_with_no_credentials() -> None:
    """Releases are read from the api with no credentials."""
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        seen.append(request)
        return httpx2.Response(
            200,
            json=[
                {
                    "tag_name": "v0.2026.11.0",
                    "draft": False,
                    "prerelease": False,
                    "published_at": "2026-11-01T12:00:00Z",
                    "html_url": "https://evil.example/phish",
                },
                {"tag_name": "0.2026.12.0rc1", "prerelease": True},
                {"tag_name": "0.2026.13.0", "draft": True},
                {"tag_name": ""},
                {"name": "no tag"},
                "junk",
            ],
        )

    releases = await provider(httpx2.MockTransport(handler)).releases(REPOSITORY)

    request = seen[0]
    assert request.url.host == "api.github.com"
    assert request.url.path == "/repos/samcorky/menagerist/releases"
    assert request.url.params["per_page"] == "30"
    assert request.headers["User-Agent"] == "menagerist/test"
    assert "authorization" not in request.headers
    assert [r.version for r in releases] == ["v0.2026.11.0", "0.2026.12.0rc1"]
    # The link is rebuilt from the tag, never taken from the response.
    assert releases[0].url == (
        "https://github.com/samcorky/menagerist/releases/tag/v0.2026.11.0"
    )
    assert releases[0].published_at is not None
    assert releases[1].prerelease
    assert releases[1].published_at is None


async def test_an_unreadable_publication_time_is_ignored() -> None:
    """An unreadable publication time is ignored."""
    body = [{"tag_name": "1.0.0", "published_at": "yesterday"}]

    releases = await provider(serving(body=body)).releases(REPOSITORY)

    assert releases[0].published_at is None


@pytest.mark.parametrize(
    ("status", "headers", "failure"),
    [
        (404, {}, CheckFailure.NOT_FOUND),
        (429, {}, CheckFailure.RATE_LIMITED),
        (403, {"x-ratelimit-remaining": "0"}, CheckFailure.RATE_LIMITED),
        (403, {}, CheckFailure.BAD_RESPONSE),
        (500, {}, CheckFailure.NETWORK),
        (503, {}, CheckFailure.NETWORK),
        (301, {}, CheckFailure.BAD_RESPONSE),
        (204, {}, CheckFailure.BAD_RESPONSE),
    ],
)
async def test_an_unsuccessful_status_is_a_fixed_failure(
    status: int, headers: dict[str, str], failure: CheckFailure
) -> None:
    """An unsuccessful status is a fixed failure."""
    with pytest.raises(ReleaseCheckError) as raised:
        await provider(serving(status, headers=headers)).releases(REPOSITORY)

    assert raised.value.failure is failure


@pytest.mark.parametrize(
    ("raised", "failure"),
    [
        (httpx2.ReadTimeout("slow"), CheckFailure.TIMEOUT),
        (httpx2.ConnectError("down"), CheckFailure.NETWORK),
    ],
)
async def test_a_transport_error_is_a_fixed_failure(
    raised: Exception, failure: CheckFailure
) -> None:
    """A transport error is a fixed failure."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        raise raised

    with pytest.raises(ReleaseCheckError) as caught:
        await provider(httpx2.MockTransport(handler)).releases(REPOSITORY)

    assert caught.value.failure is failure


@pytest.mark.parametrize("content", [b"not json", b'{"tag_name": "1.0.0"}'])
async def test_a_body_that_is_not_a_list_of_releases_is_refused(content: bytes) -> None:
    """A body that is not a list of releases is refused."""
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(200, content=content)
    )

    with pytest.raises(ReleaseCheckError) as caught:
        await provider(transport).releases(REPOSITORY)

    assert caught.value.failure is CheckFailure.BAD_RESPONSE


async def test_an_oversized_body_is_refused() -> None:
    """An oversized body is refused."""
    transport = httpx2.MockTransport(
        lambda request: httpx2.Response(200, content=b" " * (MAX_BODY_BYTES + 1))
    )

    with pytest.raises(ReleaseCheckError) as caught:
        await provider(transport).releases(REPOSITORY)

    assert caught.value.failure is CheckFailure.BAD_RESPONSE


async def test_a_redirect_off_the_api_host_is_refused() -> None:
    """A redirect off the api host is refused."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        """Handler."""
        if request.url.host == "api.github.com":
            return httpx2.Response(301, headers={"location": "https://evil.example/x"})
        return httpx2.Response(200, json=[{"tag_name": "9.9.9"}])

    with pytest.raises(ReleaseCheckError) as caught:
        await provider(httpx2.MockTransport(handler)).releases(REPOSITORY)

    assert caught.value.failure is CheckFailure.BAD_RESPONSE
