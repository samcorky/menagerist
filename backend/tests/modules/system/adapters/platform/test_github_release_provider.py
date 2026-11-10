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
from app.shared_kernel.outbound_http import (
    InMemoryOutboundHttp,
    OutboundFailure,
    OutboundHttpError,
    OutboundResponse,
)

REPOSITORY = RepositoryRef(owner="samcorky", name="menagerist")
URL = "https://api.github.com/repos/samcorky/menagerist/releases"


def serving(
    status: int = 200,
    body: object = None,
    *,
    headers: dict[str, str] | None = None,
    content: bytes | None = None,
    url: str = URL,
) -> tuple[GitHubReleaseProvider, InMemoryOutboundHttp]:
    """A provider whose one GitHub URL answers with the given response."""
    import json

    http = InMemoryOutboundHttp()
    http.reply(
        URL,
        OutboundResponse(
            url=url,
            status=status,
            headers=headers or {},
            body=content if content is not None else json.dumps(body or []).encode(),
        ),
    )
    return GitHubReleaseProvider(http), http


async def test_releases_are_read_from_the_api_with_no_credentials() -> None:
    """Releases are read from the api with no credentials."""
    provider, http = serving(
        body=[
            {
                "tag_name": "v0.2026.11.0",
                "name": "  Spring clean  ",
                "draft": False,
                "prerelease": False,
                "published_at": "2026-11-01T12:00:00Z",
                "html_url": "https://evil.example/phish",
            },
            {"tag_name": "0.2026.12.0rc1", "name": " ", "prerelease": True},
            {"tag_name": "0.2026.13.0", "draft": True},
            {"tag_name": ""},
            {"name": "no tag"},
            "junk",
        ]
    )

    releases = await provider.releases(REPOSITORY)

    (request,) = http.requests
    assert request.url == URL
    assert request.params == {"per_page": 30}
    assert request.max_bytes == MAX_BODY_BYTES
    assert not {"authorization", "user-agent"} & {k.lower() for k in request.headers}
    assert [r.version for r in releases] == ["v0.2026.11.0", "0.2026.12.0rc1"]
    # The link is rebuilt from the tag, never taken from the response.
    assert releases[0].url == (
        "https://github.com/samcorky/menagerist/releases/tag/v0.2026.11.0"
    )
    # The title is the release name, or the tag when the name is blank.
    assert [r.title for r in releases] == ["Spring clean", "0.2026.12.0rc1"]
    assert releases[0].published_at is not None
    assert releases[1].prerelease
    assert releases[1].published_at is None


async def test_an_unreadable_publication_time_is_ignored() -> None:
    """An unreadable publication time is ignored."""
    provider, _ = serving(body=[{"tag_name": "1.0.0", "published_at": "yesterday"}])

    releases = await provider.releases(REPOSITORY)

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
    provider, _ = serving(status, headers=headers)

    with pytest.raises(ReleaseCheckError) as raised:
        await provider.releases(REPOSITORY)

    assert raised.value.failure is failure


@pytest.mark.parametrize(
    ("outbound", "failure"),
    [
        (OutboundFailure.TIMEOUT, CheckFailure.TIMEOUT),
        (OutboundFailure.TOO_LARGE, CheckFailure.BAD_RESPONSE),
        (OutboundFailure.NETWORK, CheckFailure.NETWORK),
        (OutboundFailure.BLOCKED_ADDRESS, CheckFailure.NETWORK),
    ],
)
async def test_an_outbound_failure_is_a_fixed_failure(
    outbound: OutboundFailure, failure: CheckFailure
) -> None:
    """An outbound failure is a fixed failure."""
    http = InMemoryOutboundHttp()
    http.reply(URL, OutboundHttpError(outbound))

    with pytest.raises(ReleaseCheckError) as caught:
        await GitHubReleaseProvider(http).releases(REPOSITORY)

    assert caught.value.failure is failure


@pytest.mark.parametrize("content", [b"not json", b'{"tag_name": "1.0.0"}'])
async def test_a_body_that_is_not_a_list_of_releases_is_refused(content: bytes) -> None:
    """A body that is not a list of releases is refused."""
    provider, _ = serving(content=content)

    with pytest.raises(ReleaseCheckError) as caught:
        await provider.releases(REPOSITORY)

    assert caught.value.failure is CheckFailure.BAD_RESPONSE


async def test_a_response_from_another_host_is_refused() -> None:
    """A response from another host is refused."""
    provider, _ = serving(body=[{"tag_name": "9.9.9"}], url="https://evil.example/x")

    with pytest.raises(ReleaseCheckError) as caught:
        await provider.releases(REPOSITORY)

    assert caught.value.failure is CheckFailure.BAD_RESPONSE
