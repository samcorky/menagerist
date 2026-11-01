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
class PurgeItemMembershipsCommand:
    """Request to drop an item that is being hard-deleted from every collection."""

    item_id: uuid.UUID


class PurgeItemMemberships(
    CommandHandler[CollectionsUnitOfWork, PurgeItemMembershipsCommand, None]
):
    """Remove a purged item's membership rows, as they have no foreign key to it."""

    access: ClassVar[Access] = System()

    async def _handle(self, command: PurgeItemMembershipsCommand, actor: Actor) -> None:
        """Delete every membership of the item and commit."""
        async with self._uow as repos:
            await repos.memberships.purge_for_item(command.item_id)
            await self._uow.commit()
        logger.info("item memberships purged", item_id=command.item_id)
