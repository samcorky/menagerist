from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.media.ports.media_storage import MediaStoragePort, StoredFile
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class RemoveStrayMediaFilesCommand:
    """Request to delete stored files whose asset no longer exists."""

    # Only files last written before this are considered: an upload writes its file
    # before its row exists, so a recent file may belong to one still in flight.
    older_than: datetime
    # How many files are checked against the database in one query.
    batch_size: int = 100

    def __post_init__(self) -> None:
        """Refuse a naive cutoff or a batch that could never make progress."""
        if self.older_than.tzinfo is None:
            raise ValidationError("older_than must be timezone-aware")
        if self.batch_size < 1:
            raise ValidationError("The stray-file batch size must be positive")


class RemoveStrayMediaFiles(
    CommandHandler[MediaUnitOfWork, RemoveStrayMediaFilesCommand, int]
):
    """Delete stored files that no asset row refers to any more.

    Removing an asset deletes its row first and its file after the commit, so a
    failure in between, or a crash while uploading, leaves a file with no row.
    This finds those files and removes them.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: MediaUnitOfWork, guard: AccessGuard, storage: MediaStoragePort
    ) -> None:
        super().__init__(uow, guard)
        self._storage = storage

    async def _handle(
        self, command: RemoveStrayMediaFilesCommand, actor: Actor
    ) -> int:
        """Delete every stray file older than the cutoff and return how many."""
        removed = 0
        batch: list[StoredFile] = []
        async for stored in self._storage.list_files(older_than=command.older_than):
            batch.append(stored)
            if len(batch) == command.batch_size:
                removed += await self._remove_strays(batch)
                batch = []
        if batch:
            removed += await self._remove_strays(batch)
        logger.info("stray media files removed", deleted=removed)
        return removed

    async def _remove_strays(self, batch: list[StoredFile]) -> int:
        async with self._uow as repos:
            known = await repos.assets.existing_ids({s.asset_id for s in batch})
        strays = [stored for stored in batch if stored.asset_id not in known]
        for stored in strays:
            await self._storage.delete(stored.asset_id, stored.status)
        return len(strays)
