import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.add_items_to_collection import (
    MAX_ITEMS_PER_REQUEST,
)
from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.errors import CollectionNotFoundError
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class RemoveItemsFromCollectionCommand:
    """Request to take several items off a collection."""

    collection_id: uuid.UUID
    item_ids: list[uuid.UUID]


class RemoveItemsFromCollection(
    CommandHandler[CollectionsUnitOfWork, RemoveItemsFromCollectionCommand, None]
):
    """Take several items off a collection; absent items are skipped."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_WRITE)

    async def _handle(
        self, command: RemoveItemsFromCollectionCommand, actor: Actor
    ) -> None:
        """Remove the items, bump the collection's `updated_at` and commit once.

        Raises:
            ValidationError: If more than `MAX_ITEMS_PER_REQUEST` ids are given.
            CollectionNotFoundError: If the collection is missing or deleted.
            CollectionKindError: If the collection is a smart collection.
        """
        if len(command.item_ids) > MAX_ITEMS_PER_REQUEST:
            raise ValidationError(
                f"At most {MAX_ITEMS_PER_REQUEST} items can be removed at once"
            )
        async with self._uow as repos:
            collection = await repos.collections.get(
                command.collection_id, scope=self.scope(actor)
            )
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            self._guard.assert_can_modify(actor, collection.owner_id)
            collection.ensure_manual_membership()
            for item_id in dict.fromkeys(command.item_ids):
                await repos.memberships.remove(collection.id, item_id)
            collection.touch()
            await repos.collections.save(collection)
            await self._uow.commit()
        logger.info(
            "items removed from collection",
            collection_id=collection.id,
            count=len(command.item_ids),
        )
