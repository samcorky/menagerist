import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.ports.unit_of_work import CollectionsUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

# The system actor (example installs) and the id API-created collections used
# before accounts existed.
_LEGACY_OWNERS = frozenset({SYSTEM_ACTOR.id, uuid.UUID(int=1)})


@dataclass(kw_only=True)
class ClaimLegacyCollectionsCommand:
    """Request to hand ownerless and legacy-owned collections to a user."""

    owner_id: uuid.UUID


class ClaimLegacyCollections(
    GuardedCommandHandler[CollectionsUnitOfWork, ClaimLegacyCollectionsCommand, int]
):
    """Give collections that predate accounts to their first owner.

    System-level and unscoped: not reachable from any user route.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: ClaimLegacyCollectionsCommand, actor: Actor
    ) -> int:
        """Re-own every ownerless or legacy-owned collection; return the count."""
        async with self._uow as repos:
            count = await repos.collections.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            await self._uow.commit()
        logger.info("legacy collections claimed", count=count)
        return count
