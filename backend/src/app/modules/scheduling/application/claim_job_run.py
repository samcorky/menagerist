"""Claim queued work through the caller's transaction."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.scheduling.domain.job_run import JobRun
from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.jobs import Lane

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class ClaimJobRunCommand:
    """Worker capacity, claim time and an optional synchronous run target."""

    lanes: tuple[Lane, ...]
    worker_id: str
    now: datetime
    run_id: UUID | None = None


class ClaimJobRun(
    CommandHandler[SchedulingUnitOfWork, ClaimJobRunCommand, JobRun | None]
):
    """Commit a claim before execution, releasing locks even when nothing is due."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: ClaimJobRunCommand, actor: Actor) -> JobRun | None:
        async with self._uow as repos:
            run = await repos.queue.claim(
                request.lanes, request.worker_id, request.now, run_id=request.run_id
            )
            await self._uow.commit()
        return run
