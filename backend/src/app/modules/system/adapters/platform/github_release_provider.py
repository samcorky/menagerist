"""Reads a repository's releases from the public GitHub API."""

import json
from datetime import datetime
from typing import TYPE_CHECKING
from urllib.parse import quote

import httpx2

from app.modules.system.domain.release import (
    CheckFailure,
    Release,
    ReleaseCheckError,
    RepositoryRef,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

API_HOST = "api.github.com"
# One page, newest first: enough to find the highest version while bounding the
# request. A repository with more than this many newer prereleases than stable
# releases would need paging, which nothing here warrants yet.
PAGE_SIZE = 30
MAX_BODY_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 10.0


class GitHubReleaseProvider:
    """Fetches one bounded page of releases; never sends a token or follows a host."""

    def __init__(
        self,
        *,
        user_agent: str,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._user_agent = user_agent
        self._transport = transport

    async def releases(self, repository: RepositoryRef) -> list[Release]:
        """Return the repository's published releases, drafts excluded."""
        # Built from validated parts, so a build's URL can reach nothing but this
        # API.
        url = f"https://{API_HOST}/repos/{repository.slug}/releases"
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": self._user_agent,
        }
        try:
            async with (
                httpx2.AsyncClient(
                    timeout=TIMEOUT_SECONDS,
                    transport=self._transport,
                    follow_redirects=True,
                ) as client,
                client.stream(
                    "GET", url, params={"per_page": PAGE_SIZE}, headers=headers
                ) as response,
            ):
                if response.url.host != API_HOST:
                    raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)
                self._check_status(response)
                body = await self._read_bounded(response)
        except httpx2.TimeoutException as exc:
            raise ReleaseCheckError(CheckFailure.TIMEOUT) from exc
        except httpx2.HTTPError as exc:
            raise ReleaseCheckError(CheckFailure.NETWORK) from exc
        return _parse(body, repository)

    @staticmethod
    def _check_status(response: httpx2.Response) -> None:
        status = response.status_code
        if status == httpx2.codes.NOT_FOUND:
            raise ReleaseCheckError(CheckFailure.NOT_FOUND)
        exhausted = response.headers.get("x-ratelimit-remaining") == "0"
        if status == httpx2.codes.TOO_MANY_REQUESTS or (
            status == httpx2.codes.FORBIDDEN and exhausted
        ):
            raise ReleaseCheckError(CheckFailure.RATE_LIMITED)
        if status >= httpx2.codes.INTERNAL_SERVER_ERROR:
            raise ReleaseCheckError(CheckFailure.NETWORK)
        if status != httpx2.codes.OK:
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)

    @staticmethod
    async def _read_bounded(response: httpx2.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            size += len(chunk)
            if size > MAX_BODY_BYTES:
                raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)
            chunks.append(chunk)
        return b"".join(chunks)


def _parse(body: bytes, repository: RepositoryRef) -> list[Release]:
    try:
        payload = json.loads(body)
    except ValueError as exc:
        raise ReleaseCheckError(CheckFailure.BAD_RESPONSE) from exc
    if not isinstance(payload, list):
        raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)
    releases = []
    for entry in payload:
        release = _release(entry, repository) if isinstance(entry, dict) else None
        if release is not None:
            releases.append(release)
    return releases


def _release(entry: Mapping[str, object], repository: RepositoryRef) -> Release | None:
    tag = entry.get("tag_name")
    if entry.get("draft") is True or not isinstance(tag, str) or not tag:
        return None
    published = entry.get("published_at")
    try:
        published_at = (
            datetime.fromisoformat(published) if isinstance(published, str) else None
        )
    except ValueError:
        published_at = None
    # The link is rebuilt from the tag rather than trusted from the response, so a
    # release can only ever point at its own repository's page.
    return Release(
        version=tag,
        url=f"{repository.url}/releases/tag/{quote(tag, safe='')}",
        published_at=published_at,
        prerelease=entry.get("prerelease") is True,
    )
