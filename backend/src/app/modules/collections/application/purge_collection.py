import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PurgeCollectionCommand:
    """Request to hard-delete a collection and its memberships."""

    collection_id: uuid.UUID


class PurgeCollection(
    CommandHandler[CollectionsUnitOfWork, PurgeCollectionCommand, None]
):
    """Hard-delete a collection and its membership rows (for pack removal).

    Items stay. An unknown id is already gone, so a repeat is a no-op.
    """

    access: ClassVar[Access] = System()

    async def _handle(self, command: PurgeCollectionCommand, actor: Actor) -> None:
        """Delete the memberships, then the collection, and commit."""
        async with self._uow as repos:
            await repos.memberships.purge_for_collection(command.collection_id)
            await repos.collections.purge(command.collection_id)
            await self._uow.commit()
        logger.info("collection purged", collection_id=command.collection_id)
