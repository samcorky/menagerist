import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog

from app.modules.collections.domain.collection import Membership
from app.modules.collections.domain.errors import CollectionNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

MAX_ITEMS_PER_REQUEST = 500


@dataclass(kw_only=True)
class AddItemsToCollectionCommand:
    """Request to put items on a collection."""

    collection_id: uuid.UUID
    item_ids: list[uuid.UUID]


class AddItemsToCollection(
    CommandHandler[CollectionsUnitOfWork, AddItemsToCollectionCommand, int]
):
    """Put live items on a collection, skipping those already on it."""

    def __init__(self, uow: CollectionsUnitOfWork, items: ItemLookup) -> None:
        super().__init__(uow)
        self._items = items

    async def handle(self, command: AddItemsToCollectionCommand, actor: Actor) -> int:
        """Add the requested items and return how many were newly added.

        Raises:
            ValidationError: If more than `MAX_ITEMS_PER_REQUEST` ids are given,
                or any id is not a live item; nothing is added.
            CollectionNotFoundError: If the collection is missing or deleted.
        """
        if len(command.item_ids) > MAX_ITEMS_PER_REQUEST:
            raise ValidationError(
                f"At most {MAX_ITEMS_PER_REQUEST} items can be added at once"
            )
        requested = list(dict.fromkeys(command.item_ids))
        async with self._uow as repos:
            collection = await repos.collections.get(command.collection_id)
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            if not requested:
                return 0
            live = await self._items.live_ids(requested)
            missing = sorted(str(i) for i in set(requested) - live)
            if missing:
                raise ValidationError(f"Unknown or deleted items: {', '.join(missing)}")
            present = await repos.memberships.item_ids(collection.id)
            added_at = datetime.now(UTC)
            new_ids = [i for i in requested if i not in present]
            for item_id in new_ids:
                await repos.memberships.add(
                    Membership(
                        collection_id=collection.id, item_id=item_id, added_at=added_at
                    )
                )
            if new_ids:
                collection.touch()
                await repos.collections.save(collection)
                await self._uow.commit()
        logger.info(
            "items added to collection", collection_id=collection.id, count=len(new_ids)
        )
        return len(new_ids)
