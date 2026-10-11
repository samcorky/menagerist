import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.media.ports.unit_of_work import MediaUnitOfWork
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_LEGACY_OWNERS = frozenset({SYSTEM_ACTOR.id})


@dataclass(kw_only=True)
class ClaimOrphanedMediaCommand:
    """Request to hand ownerless and system-owned media to a user."""

    owner_id: uuid.UUID


class ClaimOrphanedMedia(
    CommandHandler[MediaUnitOfWork, ClaimOrphanedMediaCommand, int]
):
    """Give media that predates accounts to its first owner.

    System-level and unscoped: not reachable from any user route.
    """

    async def handle(self, command: ClaimOrphanedMediaCommand, actor: Actor) -> int:
        """Re-own every ownerless or system-owned asset; return the count."""
        async with self._uow as repos:
            count = await repos.assets.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            await self._uow.commit()
        logger.info("orphaned media claimed", count=count)
        return count
