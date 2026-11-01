from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from app.modules.media.domain.media_asset import MediaAsset
    from app.modules.media.ports.media_storage import MediaStoragePort
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CleanupExpiredMediaCommand:
    """Request to hard-delete expired staged and orphaned assets."""

    staged_before: "datetime"
    orphaned_before: "datetime"
    # How many assets one transaction removes; bounds memory and lock time.
    batch_size: int = 100

    def __post_init__(self) -> None:
        """Reject a batch that could never make progress."""
        if self.batch_size < 1:
            raise ValidationError("The cleanup batch size must be positive")


class CleanupExpiredMedia(
    CommandHandler[MediaUnitOfWork, CleanupExpiredMediaCommand, int]
):
    """Hard-delete staged and orphaned assets that have passed their TTL."""

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: MediaUnitOfWork, guard: AccessGuard, storage: MediaStoragePort
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(self, command: CleanupExpiredMediaCommand, actor: Actor) -> int:
        """Delete all expired assets and return the number removed."""
        count = 0
        for status, before in (
            (MediaStatus.STAGED, command.staged_before),
            (MediaStatus.ORPHANED, command.orphaned_before),
        ):
            while True:
                removed = await self._remove_batch(status, before, command.batch_size)
                count += removed
                if removed < command.batch_size:
                    break
        logger.info("expired media cleaned up", deleted=count)
        return count

    async def _remove_batch(
        self, status: MediaStatus, before: datetime, batch_size: int
    ) -> int:
        """Remove one batch of rows in a single transaction, then their files.

        Files go only after the commit: a failure then leaves a stray file rather
        than a row that points at nothing.
        """
        async with self._uow as repos:
            batch = await repos.assets.list_expired(
                status=status,
                before=before,
                scope=ContentFilter.everyone(),
                limit=batch_size,
            )
            if not batch:
                return 0
            for asset in batch:
                await repos.assets.delete(asset.id)
                self._uow.on_commit(self._file_remover(asset))
            await self._uow.commit()
        return len(batch)

    def _file_remover(self, asset: MediaAsset) -> Callable[[], Awaitable[None]]:
        async def remove() -> None:
            await self._storage.delete(asset.id, asset.status)

        return remove
