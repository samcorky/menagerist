"""Reads a repository's releases from the public GitHub API."""

import json
from datetime import datetime
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import quote, urlsplit

from app.modules.system.domain.release import (
    CheckFailure,
    Release,
    ReleaseCheckError,
    RepositoryRef,
)
from app.shared_kernel.outbound_http import OutboundFailure, OutboundHttpError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.shared_kernel.outbound_http import OutboundHttp, OutboundResponse

API_HOST = "api.github.com"
# One page, newest first: enough to find the highest version while bounding the
# request. A repository with more than this many newer prereleases than stable
# releases would need paging, which nothing here warrants yet.
PAGE_SIZE = 30
MAX_BODY_BYTES = 2 * 1024 * 1024
_FAILURES = {
    OutboundFailure.TIMEOUT: CheckFailure.TIMEOUT,
    OutboundFailure.TOO_LARGE: CheckFailure.BAD_RESPONSE,
}


class GitHubReleaseProvider:
    """Fetches one bounded page of releases; never sends a token or follows a host."""

    def __init__(self, http: OutboundHttp) -> None:
        self._http = http

    async def releases(self, repository: RepositoryRef) -> list[Release]:
        """Return the repository's published releases, drafts excluded."""
        # Built from validated parts, so a build's URL can reach nothing but this
        # API.
        url = f"https://{API_HOST}/repos/{repository.slug}/releases"
        try:
            response = await self._http.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                params={"per_page": PAGE_SIZE},
                max_bytes=MAX_BODY_BYTES,
            )
        except OutboundHttpError as exc:
            raise ReleaseCheckError(
                _FAILURES.get(exc.failure, CheckFailure.NETWORK)
            ) from exc
        if urlsplit(response.url).hostname != API_HOST:
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)
        self._check_status(response)
        return _parse(response.body, repository)

    @staticmethod
    def _check_status(response: OutboundResponse) -> None:
        status = response.status
        if status == HTTPStatus.NOT_FOUND:
            raise ReleaseCheckError(CheckFailure.NOT_FOUND)
        exhausted = response.headers.get("x-ratelimit-remaining") == "0"
        if status == HTTPStatus.TOO_MANY_REQUESTS or (
            status == HTTPStatus.FORBIDDEN and exhausted
        ):
            raise ReleaseCheckError(CheckFailure.RATE_LIMITED)
        if status >= HTTPStatus.INTERNAL_SERVER_ERROR:
            raise ReleaseCheckError(CheckFailure.NETWORK)
        if status != HTTPStatus.OK:
            raise ReleaseCheckError(CheckFailure.BAD_RESPONSE)


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
    name = entry.get("name")
    return Release(
        version=tag,
        title=name.strip() if isinstance(name, str) and name.strip() else tag,
        url=f"{repository.url}/releases/tag/{quote(tag, safe='')}",
        published_at=published_at,
        prerelease=entry.get("prerelease") is True,
    )
