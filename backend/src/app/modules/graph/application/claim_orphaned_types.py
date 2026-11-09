import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

# Types made through the system actor before accounts existed.
_LEGACY_OWNERS = frozenset({SYSTEM_ACTOR.id})


@dataclass(kw_only=True)
class ClaimOrphanedTypesCommand:
    """Request to hand ownerless and legacy-owned types to a user."""

    owner_id: uuid.UUID


@dataclass(kw_only=True, frozen=True)
class ClaimedTypesResult:
    """How many item types and relationship types changed owner."""

    item_types: int
    relationship_types: int


class ClaimOrphanedTypes(
    CommandHandler[GraphUnitOfWork, ClaimOrphanedTypesCommand, ClaimedTypesResult]
):
    """Give types that predate accounts to their first owner.

    System-level and unscoped: not reachable from any user route.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: ClaimOrphanedTypesCommand, actor: Actor
    ) -> ClaimedTypesResult:
        """Re-own every ownerless or system-owned item type and relationship type."""
        async with self._uow as repos:
            item_types = await repos.node_types.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            relationship_types = await repos.edge_types.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            await self._uow.commit()
        logger.info(
            "orphaned types claimed",
            item_types=item_types,
            relationship_types=relationship_types,
        )
        return ClaimedTypesResult(
            item_types=item_types, relationship_types=relationship_types
        )
