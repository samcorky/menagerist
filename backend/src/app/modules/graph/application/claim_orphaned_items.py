import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

# Items made through the system actor before accounts existed.
_LEGACY_OWNERS = frozenset({SYSTEM_ACTOR.id})


@dataclass(kw_only=True)
class ClaimOrphanedItemsCommand:
    """Request to hand ownerless and legacy-owned items and connections to a user."""

    owner_id: uuid.UUID


@dataclass(kw_only=True, frozen=True)
class ClaimedItemsResult:
    """How many items and connections changed owner."""

    items: int
    connections: int


class ClaimOrphanedItems(
    GuardedCommandHandler[
        GraphUnitOfWork, ClaimOrphanedItemsCommand, ClaimedItemsResult
    ]
):
    """Give content that predates accounts to its first owner.

    System-level and unscoped: not reachable from any user route.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: ClaimOrphanedItemsCommand, actor: Actor
    ) -> ClaimedItemsResult:
        """Re-own every ownerless or system-owned item and connection."""
        async with self._uow as repos:
            items = await repos.nodes.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            connections = await repos.edges.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            await self._uow.commit()
        logger.info("orphaned items claimed", items=items, connections=connections)
        return ClaimedItemsResult(items=items, connections=connections)
