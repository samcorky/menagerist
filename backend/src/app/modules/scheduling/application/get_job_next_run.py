"""Resolve when a registered job next fires from its effective schedule."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.domain.job_run import utc_instant
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetJobNextRunQuery:
    """The job, the instant to look beyond and the instance timezone."""

    job_key: str
    now: datetime
    timezone: str


class GetJobNextRun(UseCase[GetJobNextRunQuery, datetime | None]):
    """Return the next occurrence, or nothing when the job is off or unscheduled."""

    access: ClassVar[Access] = System()

    def __init__(
        self,
        registry: JobRegistry,
        schedules: ScheduleSource,
        evaluator: ScheduleEvaluator,
        guard: AccessGuard,
    ) -> None:
        self._guard = guard
        self._registry = registry
        self._schedules = schedules
        self._evaluator = evaluator

    async def _handle(
        self, request: GetJobNextRunQuery, actor: Actor
    ) -> datetime | None:
        job = self._registry.get(request.job_key)
        if job.schedule_key is None:
            return None
        expression = await self._schedules.schedule_for(job.schedule_key)
        if not expression:
            return None
        return await self._evaluator.next_fire(
            expression, request.timezone, after=utc_instant(request.now)
        )
