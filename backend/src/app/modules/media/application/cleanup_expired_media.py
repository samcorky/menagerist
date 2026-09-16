from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from datetime import datetime

    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CleanupExpiredMediaCommand:
    """Request to hard-delete expired staged and orphaned assets."""

    staged_before: "datetime"
    orphaned_before: "datetime"


class CleanupExpiredMedia(
    CommandHandler[MediaUnitOfWork, CleanupExpiredMediaCommand, int]
):
    """Hard-delete staged and orphaned assets that have passed their TTL."""

    def __init__(self, uow: MediaUnitOfWork, storage: MediaStoragePort) -> None:
        super().__init__(uow)
        self._storage = storage

    async def handle(self, command: CleanupExpiredMediaCommand, actor: Actor) -> int:
        """Delete all expired assets and return the number removed."""
        pairs = (
            (MediaStatus.STAGED, command.staged_before),
            (MediaStatus.ORPHANED, command.orphaned_before),
        )
        expired = []
        for status, before in pairs:
            async with self._uow as repos:
                expired.extend(
                    await repos.assets.list_expired(status=status, before=before)
                )

        count = 0
        for asset in expired:
            await self._storage.delete(asset.id, asset.status)
            async with self._uow as repos:
                await repos.assets.delete(asset.id)
                await self._uow.commit()
            count += 1
        logger.info("expired media cleaned up", deleted=count)
        return count
