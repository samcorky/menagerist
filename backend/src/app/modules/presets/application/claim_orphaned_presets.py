import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

# Presets made through the system actor before accounts existed.
_LEGACY_OWNERS = frozenset({SYSTEM_ACTOR.id})


@dataclass(kw_only=True)
class ClaimOrphanedPresetsCommand:
    """Request to hand ownerless and legacy-owned presets to a user."""

    owner_id: uuid.UUID


@dataclass(kw_only=True, frozen=True)
class ClaimedPresetsResult:
    """How many presets changed owner."""

    claimed: int


class ClaimOrphanedPresets(
    CommandHandler[PresetUnitOfWork, ClaimOrphanedPresetsCommand, ClaimedPresetsResult]
):
    """Give presets that predate accounts to their first owner.

    System-level and unscoped: not reachable from any user route.
    """

    access: ClassVar[Access] = System()

    async def _handle(
        self, command: ClaimOrphanedPresetsCommand, actor: Actor
    ) -> ClaimedPresetsResult:
        """Re-own every ownerless or system-owned preset."""
        async with self._uow as repos:
            claimed = await repos.presets.claim_orphaned(
                command.owner_id, legacy_owner_ids=_LEGACY_OWNERS
            )
            await self._uow.commit()
        logger.info("orphaned presets claimed", presets=claimed)
        return ClaimedPresetsResult(claimed=claimed)
