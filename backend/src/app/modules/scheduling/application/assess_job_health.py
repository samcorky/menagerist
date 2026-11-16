"""Find overdue, backlogged, stuck and failing jobs for the status page."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.domain.job_run import JobRun, RunStatus, utc_instant
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.jobs import Lane

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.jobs import JobDefinition

# How far back a missed occurrence is looked for. Older gaps are not reported.
_OVERDUE_LOOKBACK = timedelta(days=7)
# Recent runs examined per job; enough for a streak plus runs with no outcome.
_HISTORY_FLOOR = 10
_FAILED = {RunStatus.FAILED, RunStatus.ABANDONED}
# Skipped runs say nothing about health and in-flight ones have no outcome yet.
_NO_OUTCOME = {RunStatus.SKIPPED, RunStatus.QUEUED, RunStatus.RUNNING}


@dataclass(frozen=True, kw_only=True)
class AssessJobHealthQuery:
    """The instant to assess and the instance timezone for cron evaluation."""

    now: datetime
    timezone: str


@dataclass(frozen=True, kw_only=True)
class LaneBacklog:
    """Runs in one lane that have waited longer than their job allows.

    Each lane has a single execution slot, so the blocker is whatever is running in
    that lane now, or nothing when no worker is consuming it.
    """

    lane: Lane
    waiting: tuple[str, ...]
    oldest_wait: timedelta
    blocker: str | None


@dataclass(frozen=True, kw_only=True)
class JobHealth:
    """Names of the jobs needing attention, per condition."""

    overdue: tuple[str, ...] = ()
    backlogs: tuple[LaneBacklog, ...] = ()
    stuck: tuple[str, ...] = ()
    failing: tuple[str, ...] = ()


class AssessJobHealth(QueryHandler[JobRunReader, AssessJobHealthQuery, JobHealth]):
    """Judge each registered job against the thresholds on its own definition."""

    access: ClassVar[Access] = System()

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

    async def _handle(self, request: AssessJobHealthQuery, actor: Actor) -> JobHealth:
        now = utc_instant(request.now)
        overdue: list[str] = []
        stuck: list[str] = []
        failing: list[str] = []
        running: dict[Lane, str] = {}
        # (lane, name, how long the oldest late run has waited)
        waiting: list[tuple[Lane, str, timedelta]] = []
        for job in self._registry.all():
            name = job.title or job.job_key
            history = await self._repos.history(
                job.job_key, limit=max(_HISTORY_FLOOR, job.failure_streak * 2)
            )
            if await self._is_overdue(job, now, request.timezone):
                overdue.append(name)
            late = [
                now - run.scheduled_for
                for run in history
                if run.status is RunStatus.QUEUED
                and run.scheduled_for <= now - (job.max_lateness + job.overdue_grace)
            ]
            if late:
                waiting.append((job.lane, name, max(late)))
            for run in history:
                if run.status is not RunStatus.RUNNING:
                    continue
                running[job.lane] = name
                if (
                    run.started_at is not None
                    and now - run.started_at > job.stuck_after
                ):
                    stuck.append(name)
            if self._is_failing(job, history):
                failing.append(name)
        return JobHealth(
            overdue=tuple(overdue),
            backlogs=tuple(
                LaneBacklog(
                    lane=lane,
                    waiting=tuple(name for item, name, _ in waiting if item is lane),
                    oldest_wait=max(wait for item, _, wait in waiting if item is lane),
                    blocker=running.get(lane),
                )
                for lane in Lane
                if any(item is lane for item, _, _ in waiting)
            ),
            stuck=tuple(dict.fromkeys(stuck)),
            failing=tuple(failing),
        )

    async def _is_overdue(
        self, job: JobDefinition, now: datetime, timezone: str
    ) -> bool:
        """An occurrence that was due, with time to spare, but never submitted.

        A job with no scheduled run yet is not flagged: a fresh install looks the
        same as a scheduler fault, and the worker heartbeat covers a dead worker.
        """
        if job.schedule_key is None:
            return False
        expression = await self._schedules.schedule_for(job.schedule_key)
        if not expression:
            return False
        cutoff = now - (job.max_lateness + job.overdue_grace)
        fire = await self._evaluator.latest_fire(
            expression, timezone, after=cutoff - _OVERDUE_LOOKBACK, until=cutoff
        )
        submitted = await self._repos.last_scheduled_for(job.job_key)
        return fire is not None and submitted is not None and submitted < fire

    @staticmethod
    def _is_failing(job: JobDefinition, history: list[JobRun]) -> bool:
        """The newest `failure_streak` outcomes are all failures."""
        streak = [run for run in history if run.status not in _NO_OUTCOME][
            : job.failure_streak
        ]
        return len(streak) == job.failure_streak and all(
            run.status in _FAILED for run in streak
        )
