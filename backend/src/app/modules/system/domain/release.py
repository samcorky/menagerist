"""Release discovery: which release an instance should be told about, and how."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from app.modules.system.domain.version import Version, parse_version
from app.shared_kernel.errors import DomainError

if TYPE_CHECKING:
    from collections.abc import Iterable

# A repeat check inside this window answers from the stored result, so the manual
# action and the schedule cannot hammer the release source between them.
MIN_CHECK_INTERVAL = timedelta(minutes=1)

_GITHUB_REPOSITORY = re.compile(
    r"https://github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))"
    + r"/(?P<name>[A-Za-z0-9_.-]{1,100})"
)


class ReleaseChannel(StrEnum):
    """Which releases an instance wants to hear about."""

    STABLE = "stable"
    PREVIEW = "preview"


class CheckFailure(StrEnum):
    """Why a check could not finish; a fixed set so no upstream text is shown."""

    NETWORK = "network"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    NOT_FOUND = "not_found"
    BAD_RESPONSE = "bad_response"


class UpdateStatus(StrEnum):
    """How the installed build compares with the newest eligible release."""

    UPDATE_AVAILABLE = "update_available"
    UP_TO_DATE = "up_to_date"
    # Newer than every release on the channel, for example a preview on `stable`.
    AHEAD = "ahead"
    # A development or uncommitted build, where "older" says nothing about upgrading.
    DEVELOPMENT = "development"
    # The source answered but has no eligible release.
    NO_RELEASE = "no_release"
    # Never checked successfully, or the versions cannot be compared.
    UNKNOWN = "unknown"


class ReleaseCheckError(DomainError):
    """A release source could not be read."""

    def __init__(self, failure: CheckFailure) -> None:
        super().__init__(f"release check failed: {failure.value}")
        self.failure = failure


@dataclass(frozen=True, kw_only=True)
class RepositoryRef:
    """A GitHub repository, validated so no other host or path is ever fetched."""

    owner: str
    name: str

    @property
    def slug(self) -> str:
        """`owner/name`, as GitHub's API addresses it."""
        return f"{self.owner}/{self.name}"

    @property
    def url(self) -> str:
        """The repository's web address."""
        return f"https://github.com/{self.slug}"


def parse_github_repository(url: str | None) -> RepositoryRef | None:
    """Return the repository a build URL names, or `None` for anything else."""
    if not url:
        return None
    match = _GITHUB_REPOSITORY.fullmatch(url.strip().rstrip("/").removesuffix(".git"))
    if match is None or match["name"] in {".", ".."}:
        return None
    return RepositoryRef(owner=match["owner"], name=match["name"])


@dataclass(frozen=True, kw_only=True)
class Release:
    """A published release, as the source describes it."""

    version: str
    url: str
    published_at: datetime | None = None
    prerelease: bool = False


def select_latest(
    candidates: Iterable[Release], channel: ReleaseChannel
) -> Release | None:
    """Pick the highest version the channel allows, whatever order they arrived in.

    Publication order is not version order (a backport can be published last), and
    a tag that is not a version is skipped rather than compared as text.
    """
    best: tuple[Version, Release] | None = None
    for release in candidates:
        version = parse_version(release.version)
        if version is None:
            continue
        is_pre = release.prerelease or version.is_prerelease or version.is_devrelease
        if is_pre and channel is not ReleaseChannel.PREVIEW:
            continue
        if best is None or version > best[0]:
            best = (version, release)
    return None if best is None else best[1]


@dataclass(frozen=True, kw_only=True)
class UpdateCheck:
    """The last result for one source and channel, kept between runs."""

    source: str
    channel: ReleaseChannel
    latest: Release | None
    last_success_at: datetime | None
    last_attempt_at: datetime
    failure: CheckFailure | None = None

    @staticmethod
    def key(repository: RepositoryRef, channel: ReleaseChannel) -> str:
        """The storage key: a result is never reused across repositories or channels."""
        return f"github:{repository.slug}:{channel.value}"

    def succeeded(self, *, latest: Release | None, at: datetime) -> UpdateCheck:
        """The result of a check that read the source."""
        return UpdateCheck(
            source=self.source,
            channel=self.channel,
            latest=latest,
            last_success_at=at,
            last_attempt_at=at,
        )

    def failed(self, failure: CheckFailure, *, at: datetime) -> UpdateCheck:
        """A failed attempt: the last good answer stays, the attempt is recorded."""
        return UpdateCheck(
            source=self.source,
            channel=self.channel,
            latest=self.latest,
            last_success_at=self.last_success_at,
            last_attempt_at=at,
            failure=failure,
        )

    def is_recent(self, now: datetime) -> bool:
        """Whether the last attempt is too recent to repeat."""
        return now - self.last_attempt_at < MIN_CHECK_INTERVAL


def assess(
    installed: str, *, dirty: bool | None, check: UpdateCheck | None
) -> UpdateStatus:
    """Compare the running build with the stored result.

    Computed on every read from the installed version, so upgrading the
    application never leaves a stale "update available" in storage.
    """
    if check is None or check.last_success_at is None:
        return UpdateStatus.UNKNOWN
    if check.latest is None:
        return UpdateStatus.NO_RELEASE
    current = parse_version(installed)
    latest = parse_version(check.latest.version)
    if current is None or latest is None:
        return UpdateStatus.UNKNOWN
    if current.is_devrelease or dirty:
        return UpdateStatus.DEVELOPMENT
    if current < latest:
        return UpdateStatus.UPDATE_AVAILABLE
    if current == latest:
        return UpdateStatus.UP_TO_DATE
    return UpdateStatus.AHEAD


@dataclass(frozen=True, kw_only=True)
class ReleaseStatus:
    """What an administrator is shown about updates, derived from the stored result."""

    provider: str
    channel: ReleaseChannel
    status: UpdateStatus
    latest: Release | None
    checked_at: datetime | None
    last_attempt_at: datetime | None
    failure: CheckFailure | None

    @classmethod
    def of(
        cls,
        *,
        installed: str,
        dirty: bool | None,
        channel: ReleaseChannel,
        check: UpdateCheck | None,
    ) -> ReleaseStatus:
        """Describe `check` (or the lack of one) against the running build."""
        return cls(
            provider="github",
            channel=channel,
            status=assess(installed, dirty=dirty, check=check),
            latest=None if check is None else check.latest,
            checked_at=None if check is None else check.last_success_at,
            last_attempt_at=None if check is None else check.last_attempt_at,
            failure=None if check is None else check.failure,
        )
