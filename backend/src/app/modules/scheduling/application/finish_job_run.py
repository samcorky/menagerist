"""Persist an owned execution outcome through the common unit of work."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.scheduling.domain.job_run import RunStatus
from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class FinishJobRunCommand:
    """An execution result supplied by its current claimant."""

    run_id: UUID
    worker_id: str
    status: RunStatus
    now: datetime
    error: str | None = None


class FinishJobRun(CommandHandler[SchedulingUnitOfWork, FinishJobRunCommand, None]):
    """Commit the result only if the domain still recognises this claimant."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: FinishJobRunCommand, actor: Actor) -> None:
        async with self._uow as repos:
            await repos.recorder.finish(
                request.run_id,
                request.worker_id,
                request.status,
                request.now,
                error=request.error,
            )
            await self._uow.commit()
