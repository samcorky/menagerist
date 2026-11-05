from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

import structlog

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.presets.ports.preset_usage import PresetUsage  # noqa: TC001
from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

DEFAULT_BATCH_SIZE = 100


@dataclass(kw_only=True)
class PurgeExpiredPresetsCommand:
    """Request to hard-delete presets that were deleted before `older_than`."""

    older_than: datetime
    dry_run: bool = False
    batch_size: int = DEFAULT_BATCH_SIZE

    def __post_init__(self) -> None:
        """Refuse a naive cutoff or a batch that could never make progress."""
        if self.older_than.tzinfo is None:
            raise ValidationError("older_than must be timezone-aware")
        if self.batch_size < 1:
            raise ValidationError("batch_size must be at least 1")


@dataclass(frozen=True, kw_only=True)
class PurgeExpiredPresetsResult:
    """How many presets were (or, for a dry run, would be) hard-deleted."""

    presets: int


class PurgeExpiredPresets(
    CommandHandler[
        PresetUnitOfWork, PurgeExpiredPresetsCommand, PurgeExpiredPresetsResult
    ]
):
    """Hard-delete presets deleted before the cutoff.

    A preset that an item or relationship type still links to is left in place.
    Run this after the types have been purged, so a type removed in the same pass
    no longer holds its presets back.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: PresetUnitOfWork, guard: AccessGuard, usage: PresetUsage
    ) -> None:
        super().__init__(uow, guard)
        self._usage = usage

    async def _handle(
        self, command: PurgeExpiredPresetsCommand, actor: Actor
    ) -> PurgeExpiredPresetsResult:
        """Count (dry run) or purge expired presets in bounded batches."""
        swept = 0
        after = None
        while True:
            async with self._uow as repos:
                batch = await repos.presets.list_deleted_before(
                    command.older_than, after=after, limit=command.batch_size
                )
            if not batch:
                break
            after = batch[-1].id
            for preset in batch:
                if await self._usage.types_using(preset.id):
                    continue
                if not command.dry_run:
                    async with self._uow as repos:
                        await repos.presets.purge(preset.id)
                        await self._uow.commit()
                swept += 1
        logger.info("expired presets purged", presets=swept, dry_run=command.dry_run)
        return PurgeExpiredPresetsResult(presets=swept)
