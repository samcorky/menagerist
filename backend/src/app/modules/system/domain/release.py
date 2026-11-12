"""Release discovery: which release an instance should be told about, and how."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

from app.modules.system.domain.version import Version, parse_version
from app.shared_kernel.errors import ConflictError, DomainError

if TYPE_CHECKING:
    from collections.abc import Iterable

# A repeat check inside this window answers from the stored result, so the manual
# action and the schedule cannot hammer the release source between them.
MIN_CHECK_INTERVAL = timedelta(minutes=1)

# Revisions are compared and shown shortened, because the registry label and the
# build's own commit may not be written at the same length.
SHORT_REVISION_LENGTH = 7

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


class EdgeStatus(StrEnum):
    """How a development build compares with the published edge image."""

    # The running revision is the one the published edge image was built from.
    CURRENT = "current"
    # Edge was built from a different revision, so a newer image is available.
    BEHIND = "behind"
    # Edge could not be read, or this build has no revision to compare.
    UNKNOWN = "unknown"


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


class UpdateChecksDisabledError(ConflictError):
    """Update checks are turned off by the deployment, so nothing is contacted."""

    def __init__(self) -> None:
        super().__init__("update checks are turned off by the deployment")


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


@dataclass(frozen=True, kw_only=True)
class ImageRef:
    """A published container image, as a registry addresses it."""

    repository: str
    tag: str

    @property
    def reference(self) -> str:
        """`repository:tag`, for logs and display."""
        return f"{self.repository}:{self.tag}"


# The tag a development build is published under; it moves with every build, which
# is why the revision is read from the registry rather than baked in.
EDGE_TAG = "edge"


def edge_image(repository: RepositoryRef) -> ImageRef:
    """The edge image a repository publishes, named the way its packages are."""
    return ImageRef(repository=repository.slug.lower(), tag=EDGE_TAG)


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
    # The release's own name; the source falls back to the tag when it has none.
    title: str
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
    # The revision the published edge image was built from, when it could be read.
    # Kept beside the release because one check discovers both.
    edge_revision: str | None = None

    @staticmethod
    def key(repository: RepositoryRef, channel: ReleaseChannel) -> str:
        """The storage key: a result is never reused across repositories or channels."""
        return f"github:{repository.slug}:{channel.value}"

    def succeeded(
        self, *, latest: Release | None, at: datetime, edge_revision: str | None = None
    ) -> UpdateCheck:
        """The result of a check that read the source."""
        return UpdateCheck(
            source=self.source,
            channel=self.channel,
            latest=latest,
            last_success_at=at,
            last_attempt_at=at,
            edge_revision=edge_revision,
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
            edge_revision=self.edge_revision,
        )

    def is_recent(self, now: datetime) -> bool:
        """Whether the last attempt is too recent to repeat."""
        return now - self.last_attempt_at < MIN_CHECK_INTERVAL


def short_revision(revision: str | None) -> str | None:
    """A revision shortened for display, or `None` when there is nothing to show."""
    trimmed = "" if revision is None else revision.strip()
    return trimmed[:SHORT_REVISION_LENGTH] or None


def is_development(installed: str, *, dirty: bool | None) -> bool:
    """Whether this build is a development or uncommitted one.

    The one definition of the build a version comparison says nothing about.
    """
    version = parse_version(installed)
    return bool(dirty) or (version is not None and version.is_devrelease)


def is_comparable_with_edge(
    installed: str, *, dirty: bool | None, revision: str | None
) -> bool:
    """Whether reading the edge image could tell this build anything.

    Narrower than `is_development`: an uncommitted build is not the published image
    whatever its commit says, and a build with no revision has nothing to compare,
    so in both cases the registry read would be thrown away.
    """
    if dirty or short_revision(revision) is None:
        return False
    return is_development(installed, dirty=dirty)


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
    if is_development(installed, dirty=dirty):
        return UpdateStatus.DEVELOPMENT
    if current < latest:
        return UpdateStatus.UPDATE_AVAILABLE
    if current == latest:
        return UpdateStatus.UP_TO_DATE
    return UpdateStatus.AHEAD


@dataclass(frozen=True, kw_only=True)
class EdgeComparison:
    """Whether a development build is the published edge image.

    Only a yes or no, with both revisions to show: how many builds apart they are is
    not something the registry can answer, and a commit count is not a build count.
    """

    status: EdgeStatus
    installed_revision: str | None
    edge_revision: str | None
    compare_url: str | None = None

    @classmethod
    def of(
        cls,
        *,
        repository: RepositoryRef,
        installed_revision: str | None,
        dirty: bool | None,
        check: UpdateCheck | None,
    ) -> EdgeComparison:
        """Compare the running revision with the edge revision last read."""
        installed = short_revision(installed_revision)
        edge = short_revision(None if check is None else check.edge_revision)
        # Uncommitted changes make the running code no image at all, so comparing its
        # commit with edge's would answer a question that was not asked.
        if installed is None or edge is None or dirty:
            return cls(
                status=EdgeStatus.UNKNOWN,
                installed_revision=installed,
                edge_revision=edge,
            )
        if installed == edge:
            return cls(
                status=EdgeStatus.CURRENT,
                installed_revision=installed,
                edge_revision=edge,
            )
        # The real commit list is a click away rather than counted here, where a
        # rebased or forked build would make any count meaningless.
        return cls(
            status=EdgeStatus.BEHIND,
            installed_revision=installed,
            edge_revision=edge,
            compare_url=f"{repository.url}/compare/{installed}...{edge}",
        )


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
    # Only for a development build, where a version comparison says nothing.
    edge: EdgeComparison | None = None

    @classmethod
    def of(
        cls,
        *,
        installed: str,
        dirty: bool | None,
        channel: ReleaseChannel,
        check: UpdateCheck | None,
        repository: RepositoryRef | None = None,
        installed_revision: str | None = None,
    ) -> ReleaseStatus:
        """Describe `check` (or the lack of one) against the running build."""
        status = assess(installed, dirty=dirty, check=check)
        edge = (
            EdgeComparison.of(
                repository=repository,
                installed_revision=installed_revision,
                dirty=dirty,
                check=check,
            )
            if status is UpdateStatus.DEVELOPMENT and repository is not None
            else None
        )
        return cls(
            provider="github",
            channel=channel,
            status=status,
            latest=None if check is None else check.latest,
            checked_at=None if check is None else check.last_success_at,
            last_attempt_at=None if check is None else check.last_attempt_at,
            failure=None if check is None else check.failure,
            edge=edge,
        )
