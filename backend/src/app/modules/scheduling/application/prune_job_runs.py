"""Retain a bounded history of completed executions for each job."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class PruneJobRunsCommand:
    """The completed-run quota for each job, and when a silent worker is forgotten."""

    keep_per_job: int
    worker_heartbeats_before: datetime

    def __post_init__(self) -> None:
        """Require at least one completed run to remain."""
        if self.keep_per_job < 1:
            raise ValidationError("Run history retention must be positive")


class PruneJobRuns(CommandHandler[SchedulingUnitOfWork, PruneJobRunsCommand, int]):
    """Apply retention within the scheduling unit of work."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: PruneJobRunsCommand, actor: Actor) -> int:
        async with self._uow as repos:
            removed = await repos.recorder.prune_history(
                keep_per_job=request.keep_per_job
            )
            await repos.recorder.prune_worker_heartbeats(
                before=request.worker_heartbeats_before
            )
            await self._uow.commit()
        return removed
