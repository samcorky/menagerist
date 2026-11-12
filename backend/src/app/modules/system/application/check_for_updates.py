from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.release import (
    ReleaseChannel,
    ReleaseCheckError,
    UpdateCheck,
    UpdateChecksDisabledError,
    edge_image,
    is_comparable_with_edge,
    parse_github_repository,
    select_latest,
)
from app.modules.system.ports.unit_of_work import SystemUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.system.domain.release import RepositoryRef
    from app.modules.system.ports.app_info_port import AppInfoPort
    from app.modules.system.ports.published_image_provider import PublishedImageProvider
    from app.modules.system.ports.release_provider import ReleaseProvider
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class CheckForUpdatesCommand:
    """The channel to look at and the instant the check is made."""

    channel: ReleaseChannel
    now: datetime


class CheckForUpdates(
    CommandHandler[SystemUnitOfWork, CheckForUpdatesCommand, UpdateCheck | None]
):
    """Ask the release source for the newest eligible release and keep the answer.

    The one place a release is discovered: the Check now button and the scheduled
    job both call it. A failure is recorded, never raised, and leaves the last good
    answer in place. Returns `None` when this build names no supported repository.

    Also the one place the deployment switch is enforced, so a stale client or a
    direct API call cannot make the instance contact github.com or ghcr.io.
    """

    access: ClassVar[Access] = Requires(SystemPermission.CHECK_FOR_UPDATES)

    def __init__(
        self,
        uow: SystemUnitOfWork,
        guard: AccessGuard,
        *,
        app_info: AppInfoPort,
        provider: ReleaseProvider,
        images: PublishedImageProvider,
        enabled: bool = True,
    ) -> None:
        super().__init__(uow, guard)
        self._app_info = app_info
        self._provider = provider
        self._images = images
        self._enabled = enabled

    async def _handle(
        self, command: CheckForUpdatesCommand, actor: Actor
    ) -> UpdateCheck | None:
        if not self._enabled:
            raise UpdateChecksDisabledError
        app_info = await self._app_info.load()
        repository = parse_github_repository(app_info.repository_url)
        if repository is None:
            return None
        key = UpdateCheck.key(repository, command.channel)

        async with self._uow as repos:
            previous = await repos.updates.get(key)
        if previous is not None and previous.is_recent(command.now):
            return previous
        previous = previous or UpdateCheck(
            source=repository.slug,
            channel=command.channel,
            latest=None,
            last_success_at=None,
            last_attempt_at=command.now,
        )

        # The request is made with no transaction open, so a slow source never holds
        # a database connection.
        try:
            candidates = await self._provider.releases(repository)
        except ReleaseCheckError as exc:
            outcome = previous.failed(exc.failure, at=command.now)
            logger.warning(
                "release check failed",
                source=repository.slug,
                failure=exc.failure.value,
            )
        else:
            latest = select_latest(candidates, command.channel)
            edge_revision = await self._edge_revision(
                repository,
                app_info.version,
                dirty=app_info.dirty,
                revision=app_info.commit_sha,
            )
            outcome = previous.succeeded(
                latest=latest, at=command.now, edge_revision=edge_revision
            )
            logger.info(
                "release check finished",
                source=repository.slug,
                channel=command.channel.value,
                latest=None if latest is None else latest.version,
                title=None if latest is None else latest.title,
                edge_revision=edge_revision,
            )

        async with self._uow as repos:
            await repos.updates.save(key, outcome)
            await self._uow.commit()
        return outcome

    async def _edge_revision(
        self,
        repository: RepositoryRef,
        installed: str,
        *,
        dirty: bool | None,
        revision: str | None,
    ) -> str | None:
        """The revision the published edge image was built from.

        Read only when the answer could tell this build something, so the check
        never fetches what the Status page would discard. A registry that cannot be
        read leaves the edge row unknown rather than failing the release check,
        which succeeded on its own terms.
        """
        if not is_comparable_with_edge(installed, dirty=dirty, revision=revision):
            return None
        image = edge_image(repository)
        try:
            return await self._images.revision(image)
        except ReleaseCheckError as exc:
            logger.warning(
                "edge image read failed",
                image=image.reference,
                failure=exc.failure.value,
            )
            return None
