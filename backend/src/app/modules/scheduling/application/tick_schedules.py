"""Observe deployment schedules and submit the latest eligible occurrences."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.scheduling.domain.job_run import JobRun, utc_instant
from app.modules.scheduling.domain.schedule import due_fire
from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.jobs import MissedRun

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.domain.schedule_cursor import ScheduleCursor
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


logger = structlog.get_logger()


@dataclass(frozen=True, kw_only=True)
class TickSchedulesCommand:
    """A worker-supplied clock and instance timezone."""

    now: datetime
    timezone: str


class TickSchedules(
    CommandHandler[SchedulingUnitOfWork, TickSchedulesCommand, list[JobRun]]
):
    """Submit eligible fires and advance their cursors in the same transaction."""

    access: ClassVar[Access] = System()

    def __init__(
        self,
        uow: SchedulingUnitOfWork,
        guard: AccessGuard,
        registry: JobRegistry,
        schedules: ScheduleSource,
        evaluator: ScheduleEvaluator,
    ) -> None:
        super().__init__(uow, guard)
        self._registry = registry
        self._schedules = schedules
        self._evaluator = evaluator

    async def _handle(
        self, request: TickSchedulesCommand, actor: Actor
    ) -> list[JobRun]:
        now = utc_instant(request.now)
        submitted: list[JobRun] = []
        changed: list[tuple[ScheduleCursor, ScheduleCursor]] = []
        async with self._uow as repos:
            for job in sorted(self._registry.all(), key=lambda item: item.job_key):
                if job.schedule_key is None:
                    continue
                expression = (
                    await self._schedules.schedule_for(job.schedule_key) or None
                )
                cursor = await repos.cursors.observe(
                    job.job_key,
                    expression=expression,
                    timezone=request.timezone,
                    now=now,
                )
                if cursor.changed_from is not None:
                    changed.append((cursor.changed_from, cursor))
                if expression and cursor.checked_until < now:
                    grace = (
                        job.max_lateness
                        if job.missed_run is MissedRun.RUN_ONCE
                        else timedelta(minutes=1)
                    )
                    after = max(
                        cursor.checked_until, now - grace - timedelta(microseconds=1)
                    )
                    latest = await self._evaluator.latest_fire(
                        expression, request.timezone, after=after, until=now
                    )
                    fire = due_fire(
                        latest,
                        watermark=cursor.checked_until,
                        now=now,
                        missed=job.missed_run,
                        max_lateness=job.max_lateness,
                    )
                    if fire is not None:
                        submitted.append(
                            await repos.queue.enqueue(JobRun.for_schedule(job, fire))
                        )
                await repos.cursors.advance(job.job_key, now)
            await self._uow.commit()
        for previous, cursor in changed:
            await self._log_change(previous, cursor, now)
        return submitted

    async def _log_change(
        self, previous: ScheduleCursor, cursor: ScheduleCursor, now: datetime
    ) -> None:
        """Record that a job's schedule or timezone changed, and when it runs next."""
        next_run = None
        if cursor.expression:
            try:
                fire = await self._evaluator.next_fire(
                    cursor.expression, cursor.timezone, after=now
                )
            except ValidationError:
                fire = None
            next_run = fire.isoformat() if fire else None
        logger.info(
            "job schedule changed",
            job_key=cursor.job_key,
            previous_schedule=previous.expression,
            schedule=cursor.expression,
            previous_timezone=previous.timezone,
            timezone=cursor.timezone,
            next_run=next_run,
        )
