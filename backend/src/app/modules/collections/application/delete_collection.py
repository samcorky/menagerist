import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteCollectionCommand:
    """Request to soft-delete a collection."""

    collection_id: uuid.UUID


class DeleteCollection(
    CommandHandler[CollectionsUnitOfWork, DeleteCollectionCommand, None]
):
    """Soft-delete a collection, leaving its memberships and items alone."""

    async def handle(self, command: DeleteCollectionCommand, actor: Actor) -> None:
        """Soft-delete the collection identified by `command` and commit."""
        async with self._uow as repos:
            collection = await repos.collections.get(command.collection_id)
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            collection.soft_delete()
            await repos.collections.save(collection)
            await self._uow.commit()
        logger.info("collection deleted", collection_id=command.collection_id)
