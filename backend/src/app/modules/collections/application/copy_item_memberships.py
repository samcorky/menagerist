import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import CollectionKind, Membership

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CopyItemMembershipsCommand:
    """Request to put a duplicate on the manual collections of its original."""

    source_id: uuid.UUID
    target_id: uuid.UUID


class CopyItemMemberships(
    CommandHandler[CollectionsUnitOfWork, CopyItemMembershipsCommand, int]
):
    """Add the target item to every live manual collection holding the source.

    Smart collections are skipped: they hold whatever matches their rules, so the
    duplicate joins them on its own if it fits.
    """

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_WRITE)

    def __init__(
        self, uow: CollectionsUnitOfWork, guard: AccessGuard, items: ItemLookup
    ) -> None:
        super().__init__(uow, guard)
        self._items = items

    async def _handle(self, command: CopyItemMembershipsCommand, actor: Actor) -> int:
        """Add the target to each collection and return how many it joined.

        Raises:
            ValidationError: If the target is not a live item the
                actor can see; nothing is added.
        """
        scope = self.scope(actor)
        if command.target_id not in await self._items.live_ids(
            [command.target_id], scope
        ):
            raise ValidationError(f"Unknown or deleted item: {command.target_id}")
        joined = 0
        async with self._uow as repos:
            added_at = datetime.now(UTC)
            for collection_id in sorted(
                await repos.memberships.collection_ids_for(
                    command.source_id, scope=scope
                )
            ):
                collection = await repos.collections.get(collection_id, scope=scope)
                if collection is None or collection.kind is not CollectionKind.MANUAL:
                    continue
                self._guard.assert_can_modify(actor, collection.owner_id)
                await repos.memberships.add(
                    Membership(
                        collection_id=collection.id,
                        item_id=command.target_id,
                        added_at=added_at,
                    )
                )
                collection.touch()
                await repos.collections.save(collection)
                joined += 1
            if joined:
                await self._uow.commit()
        logger.info(
            "item added to collections of its original",
            source_id=command.source_id,
            target_id=command.target_id,
            count=joined,
        )
        return joined
