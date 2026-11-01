from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.system.application.permissions import SystemPermission
from app.modules.system.domain.release import (
    ReleaseChannel,
    ReleaseCheckError,
    UpdateCheck,
    parse_github_repository,
    select_latest,
)
from app.modules.system.ports.unit_of_work import SystemUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.system.ports.app_info_port import AppInfoPort
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
    """

    access: ClassVar[Access] = Requires(SystemPermission.CHECK_FOR_UPDATES)

    def __init__(
        self,
        uow: SystemUnitOfWork,
        guard: AccessGuard,
        *,
        app_info: AppInfoPort,
        provider: ReleaseProvider,
    ) -> None:
        super().__init__(uow, guard)
        self._app_info = app_info
        self._provider = provider

    async def _handle(
        self, command: CheckForUpdatesCommand, actor: Actor
    ) -> UpdateCheck | None:
        repository = parse_github_repository(
            (await self._app_info.load()).repository_url
        )
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
            outcome = previous.succeeded(latest=latest, at=command.now)
            logger.info(
                "release check finished",
                source=repository.slug,
                channel=command.channel.value,
                latest=None if latest is None else latest.version,
            )

        async with self._uow as repos:
            await repos.updates.save(key, outcome)
            await self._uow.commit()
        return outcome
