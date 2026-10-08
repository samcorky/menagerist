import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdateCollectionCommand:
    """Request to update a collection's name or description. `slug` is immutable."""

    collection_id: uuid.UUID
    name: str | None = None
    description: str | None = None


class UpdateCollection(
    CommandHandler[CollectionsUnitOfWork, UpdateCollectionCommand, Collection]
):
    """Update an existing collection's editable fields."""

    async def handle(
        self, command: UpdateCollectionCommand, actor: Actor
    ) -> Collection:
        """Apply `command`'s changes to the collection and commit.

        A blank `description` clears it; `None` leaves it unchanged.

        Raises:
            CollectionNotFoundError: If the collection does not exist or is deleted.
            InvalidCollectionError: If the new name is not 1 to 120 characters.
        """
        async with self._uow as repos:
            collection = await repos.collections.get(command.collection_id)
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            if command.name is not None:
                collection.rename(command.name)
            if command.description is not None:
                collection.description = command.description.strip() or None
            collection.touch()
            await repos.collections.save(collection)
            await self._uow.commit()
        logger.info("collection updated", collection_id=command.collection_id)
        return collection
