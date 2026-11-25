"""Queue a job for work a person started in another module."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.scheduling.domain.errors import OnDemandNotAllowedError
from app.modules.scheduling.domain.job_run import JobRun, utc_instant
from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.jobs import Overlap

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class QueueJobRunCommand:
    """The on-demand job, the person whose work it is, and when they asked."""

    job_key: str
    requested_by: UUID
    now: datetime


class QueueJobRun(CommandHandler[SchedulingUnitOfWork, QueueJobRunCommand, JobRun]):
    """Queue a run of a job, reusing one still waiting to start.

    Unlike `RunJobNow`, a run already under way is not reused: it may have looked
    for work before this request's was recorded. The owning module checks that the
    person may start the work; this only puts the job on the queue, so it is for the
    system actor, through the `JobQueue` bridge.

    Raises:
        UnknownJobError: no job has the key.
        OnDemandNotAllowedError: the job does not coalesce its runs.
    """

    access: ClassVar[Access] = System()

    def __init__(
        self, uow: SchedulingUnitOfWork, guard: AccessGuard, registry: JobRegistry
    ) -> None:
        super().__init__(uow, guard)
        self._registry = registry

    async def _handle(self, request: QueueJobRunCommand, actor: Actor) -> JobRun:
        job = self._registry.get(request.job_key)
        if job.overlap is not Overlap.COALESCE:
            # Skipping strands work recorded after a drain looked; queueing stacks
            # runs that find nothing left to do.
            raise OnDemandNotAllowedError(
                f"Job {job.job_key} must coalesce its runs to be queued on demand."
            )
        run = JobRun.create(
            job_key=job.job_key,
            scheduled_for=utc_instant(request.now),
            lane=job.lane,
            overlap=job.overlap,
            requested_by=request.requested_by,
        )
        async with self._uow as repos:
            # Coalescing reuses only a run still waiting: one already running may
            # have looked for work before this request's work was recorded.
            accepted = await repos.queue.enqueue(run)
            await self._uow.commit()
        return accepted
