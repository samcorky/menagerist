"""Submit an administrative manual run through the transaction-bound queue."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.errors import RunNowNotAllowedError
from app.modules.scheduling.domain.job_run import JobRun, utc_instant
from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class RunJobNowCommand:
    """The registered job key and request timestamp."""

    job_key: str
    now: datetime


class RunJobNow(CommandHandler[SchedulingUnitOfWork, RunJobNowCommand, JobRun]):
    """Reuse active work for repeated requests instead of stacking manual runs."""

    access: ClassVar[Access] = Requires(SchedulingPermission.RUN)

    def __init__(
        self, uow: SchedulingUnitOfWork, guard: AccessGuard, registry: JobRegistry
    ) -> None:
        super().__init__(uow, guard)
        self._registry = registry

    async def _handle(self, request: RunJobNowCommand, actor: Actor) -> JobRun:
        job = self._registry.get(request.job_key)
        if not job.run_now_allowed:
            raise RunNowNotAllowedError(job.job_key)
        run = JobRun.create(
            job_key=job.job_key,
            scheduled_for=utc_instant(request.now),
            lane=job.lane,
            overlap=job.overlap,
            requested_by=None if actor.id == SYSTEM_ACTOR.id else actor.id,
        )
        async with self._uow as repos:
            accepted = await repos.queue.enqueue(run, deduplicate_active=True)
            await self._uow.commit()
        return accepted
