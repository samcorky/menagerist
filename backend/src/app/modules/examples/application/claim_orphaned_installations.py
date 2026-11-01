import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.examples.ports.unit_of_work import ExampleUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_LEGACY_OWNERS = frozenset({SYSTEM_ACTOR.id})


@dataclass(kw_only=True)
class ClaimOrphanedInstallationsCommand:
    """Request to hand ownerless and system-owned installations to a user."""

    owner_id: uuid.UUID


class ClaimOrphanedInstallations(
    CommandHandler[ExampleUnitOfWork, ClaimOrphanedInstallationsCommand, int]
):
    """Give example installations that predate accounts to their first owner.

    System-level and unscoped: not reachable from any user route.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: ClaimOrphanedInstallationsCommand, actor: Actor
    ) -> int:
        """Re-own every ownerless or system-owned installation; return the count."""
        async with self._uow as repos:
            count = await repos.installations.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            await self._uow.commit()
        logger.info("orphaned installations claimed", count=count)
        return count
