from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.app_info import AppInfo
from app.modules.system.domain.release import (
    ReleaseChannel,
    ReleaseStatus,
    UpdateCheck,
    parse_github_repository,
)
from app.modules.system.ports.app_info_port import AppInfoPort
from app.modules.system.ports.update_check_store import UpdateCheckStore
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class VersionDetailSources:
    """What the full version report reads: the build and the stored release check."""

    app_info: AppInfoPort
    updates: UpdateCheckStore


@dataclass(kw_only=True, frozen=True)
class GetVersionDetailQuery:
    """Request for the full build provenance and update status of the instance."""

    channel: ReleaseChannel = ReleaseChannel.STABLE


@dataclass(kw_only=True, frozen=True)
class VersionDetail:
    """The installed build, and what is known about newer releases."""

    app_info: AppInfo
    # `None` when this build names no repository a release check can read.
    release: ReleaseStatus | None


class GetVersionDetail(
    QueryHandler[VersionDetailSources, GetVersionDetailQuery, VersionDetail]
):
    """Report commit, branch, migration head and update status, for administrators.

    Reads the stored result only; it never contacts the release source.
    """

    access: ClassVar[Access] = Requires(SystemPermission.READ_DIAGNOSTICS)

    async def _handle(
        self, query: GetVersionDetailQuery, actor: Actor
    ) -> VersionDetail:
        """Return the application's build metadata with its cached release status."""
        app_info = await self._repos.app_info.load()
        repository = parse_github_repository(app_info.repository_url)
        if repository is None:
            return VersionDetail(app_info=app_info, release=None)
        check: UpdateCheck | None = await self._repos.updates.get(
            UpdateCheck.key(repository, query.channel)
        )
        release = ReleaseStatus.of(
            installed=app_info.version,
            dirty=app_info.dirty,
            channel=query.channel,
            check=check,
        )
        return VersionDetail(app_info=app_info, release=release)
