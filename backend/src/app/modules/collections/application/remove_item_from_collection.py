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
class RemoveItemFromCollectionCommand:
    """Request to take an item off a collection."""

    collection_id: uuid.UUID
    item_id: uuid.UUID


class RemoveItemFromCollection(
    CommandHandler[CollectionsUnitOfWork, RemoveItemFromCollectionCommand, None]
):
    """Take an item off a collection; removing an absent item is a no-op."""

    async def handle(
        self, command: RemoveItemFromCollectionCommand, actor: Actor
    ) -> None:
        """Remove the item, bump the collection's `updated_at` and commit.

        Raises:
            CollectionNotFoundError: If the collection is missing or deleted.
        """
        async with self._uow as repos:
            collection = await repos.collections.get(command.collection_id)
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            await repos.memberships.remove(collection.id, command.item_id)
            collection.touch()
            await repos.collections.save(collection)
            await self._uow.commit()
        logger.info(
            "item removed from collection",
            collection_id=collection.id,
            item_id=command.item_id,
        )
