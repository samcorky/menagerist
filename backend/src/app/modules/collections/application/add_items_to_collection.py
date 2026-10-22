import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.domain.collection import Membership
from app.modules.collections.domain.errors import CollectionNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

MAX_ITEMS_PER_REQUEST = 500


@dataclass(kw_only=True)
class AddItemsToCollectionCommand:
    """Request to put items on a collection."""

    collection_id: uuid.UUID
    item_ids: list[uuid.UUID]


class AddItemsToCollection(
    GuardedCommandHandler[CollectionsUnitOfWork, AddItemsToCollectionCommand, int]
):
    """Put live items on a collection, skipping those already on it."""

    access: ClassVar[Access] = Content()

    def __init__(
        self, uow: CollectionsUnitOfWork, guard: AccessGuard, items: ItemLookup
    ) -> None:
        super().__init__(uow, guard)
        self._items = items

    async def _handle(self, command: AddItemsToCollectionCommand, actor: Actor) -> int:
        """Add the requested items and return how many were newly added.

        Raises:
            ValidationError: If more than `MAX_ITEMS_PER_REQUEST` ids are given,
                or any id is not a live item the actor can see; nothing is added.
            CollectionNotFoundError: If the collection is missing, deleted or not
                the actor's.
            CollectionKindError: If the collection is a smart collection.
        """
        if len(command.item_ids) > MAX_ITEMS_PER_REQUEST:
            raise ValidationError(
                f"At most {MAX_ITEMS_PER_REQUEST} items can be added at once"
            )
        requested = list(dict.fromkeys(command.item_ids))
        scope = self.scope(actor)
        async with self._uow as repos:
            collection = await repos.collections.get(command.collection_id, scope=scope)
            if collection is None:
                raise CollectionNotFoundError(
                    f"Collection {command.collection_id} not found"
                )
            self._guard.assert_can_modify(actor, collection.owner_id)
            collection.ensure_manual_membership()
            if not requested:
                return 0
            live = await self._items.live_ids(requested, scope)
            missing = sorted(str(i) for i in set(requested) - live)
            if missing:
                raise ValidationError(f"Unknown or deleted items: {', '.join(missing)}")
            present = await repos.memberships.item_ids(collection.id, scope=scope)
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
