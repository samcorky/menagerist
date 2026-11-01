from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    import uuid

    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

DEFAULT_BATCH_SIZE = 100


@dataclass(kw_only=True)
class PurgeExpiredCollectionsCommand:
    """Request to hard-delete collections that were deleted before `older_than`."""

    older_than: datetime
    dry_run: bool = False
    batch_size: int = DEFAULT_BATCH_SIZE

    def __post_init__(self) -> None:
        """Refuse a naive cutoff or a batch that could never make progress."""
        if self.older_than.tzinfo is None:
            raise ValidationError("older_than must be timezone-aware")
        if self.batch_size < 1:
            raise ValidationError("batch_size must be at least 1")


@dataclass(frozen=True, kw_only=True)
class PurgeExpiredCollectionsResult:
    """How many collections were (or, for a dry run, would be) hard-deleted."""

    collections: int


class PurgeExpiredCollections(
    CommandHandler[
        CollectionsUnitOfWork,
        PurgeExpiredCollectionsCommand,
        PurgeExpiredCollectionsResult,
    ]
):
    """Hard-delete every owner's collections deleted before the cutoff.

    Memberships go with each collection; items stay. Live collections are never
    touched, and one restored since it was listed is skipped.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: PurgeExpiredCollectionsCommand, actor: Actor
    ) -> PurgeExpiredCollectionsResult:
        """Count (dry run) or purge expired collections in bounded batches."""
        if command.dry_run:
            async with self._uow as repos:
                return PurgeExpiredCollectionsResult(
                    collections=await repos.collections.count_deleted_before(
                        command.older_than
                    )
                )
        purged = 0
        while True:
            async with self._uow as repos:
                batch = await repos.collections.list_deleted_before(
                    command.older_than, limit=command.batch_size
                )
            if not batch:
                break
            for collection in batch:
                if await self._purge_one(collection.id, command.older_than):
                    purged += 1
        logger.info("expired collections purged", collections=purged)
        return PurgeExpiredCollectionsResult(collections=purged)

    async def _purge_one(self, collection_id: uuid.UUID, cutoff: datetime) -> bool:
        """Purge one collection if it is still deleted before the cutoff."""
        async with self._uow as repos:
            collection = await repos.collections.get_deleted(
                collection_id, scope=ContentFilter.everyone()
            )
            if collection is None or not (
                collection.deleted_at and collection.deleted_at < cutoff
            ):
                return False
            await repos.memberships.purge_for_collection(collection.id)
            await repos.collections.purge(collection.id)
            await self._uow.commit()
        return True
