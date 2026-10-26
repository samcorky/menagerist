"""Read-only job metadata, active work and next-fire previews."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.job_run import JobRun, utc_instant
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.jobs import JobDefinition

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class ListJobsQuery:
    """The instant and instance timezone used for next-run previews."""

    now: datetime
    timezone: str


@dataclass(frozen=True, kw_only=True)
class JobStatus:
    """A job definition with its effective schedule and execution state."""

    definition: JobDefinition
    expression: str | None
    next_run_at: datetime | None
    active_run: JobRun | None


class ListJobs(QueryHandler[JobRunReader, ListJobsQuery, list[JobStatus]]):
    """List registered jobs without initialising or advancing schedule cursors."""

    access: ClassVar[Access] = Requires(SchedulingPermission.READ)

    def __init__(
        self,
        repos: JobRunReader,
        guard: AccessGuard,
        registry: JobRegistry,
        schedules: ScheduleSource,
        evaluator: ScheduleEvaluator,
    ) -> None:
        super().__init__(repos, guard)
        self._registry = registry
        self._schedules = schedules
        self._evaluator = evaluator

    async def _handle(self, request: ListJobsQuery, actor: Actor) -> list[JobStatus]:
        now = utc_instant(request.now)
        statuses = []
        for job in self._registry.all():
            expression = (
                (await self._schedules.schedule_for(job.schedule_key) or None)
                if job.schedule_key is not None
                else None
            )
            next_run = (
                await self._evaluator.next_fire(expression, request.timezone, after=now)
                if expression
                else None
            )
            statuses.append(
                JobStatus(
                    definition=job,
                    expression=expression,
                    next_run_at=next_run,
                    active_run=await self._repos.active_run(job.job_key),
                )
            )
        return statuses
