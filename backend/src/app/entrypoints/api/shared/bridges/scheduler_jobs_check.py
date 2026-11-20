"""Bridge scheduled-job health into warn-only system readiness diagnostics."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.job_catalogue import (
    get_job_catalogue,
    get_schedule_source,
)
from app.modules.scheduling.adapters.persistence.job_run_reader import (
    SqlAlchemyJobRunReader,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.application.assess_job_health import (
    AssessJobHealth,
    AssessJobHealthQuery,
    JobHealth,
    LaneBacklog,
)
from app.modules.system.domain.readiness import CheckObservation, CheckStatus
from app.platform.config.server import get_server_settings
from app.platform.database import DATABASE_OUTAGE_ERRORS
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.modules.scheduling.ports.schedule_source import ScheduleSource

logger = structlog.get_logger(__name__)

OVERDUE_KEY = "scheduler:overdueJobs"
STUCK_KEY = "scheduler:stuckJobs"
FAILING_KEY = "scheduler:failingJobs"
QUEUE_KEYS = {
    Lane.DEFAULT: "scheduler:defaultQueue",
    Lane.HEAVY: "scheduler:heavyQueue",
}
ALL_KEYS = (OVERDUE_KEY, *QUEUE_KEYS.values(), STUCK_KEY, FAILING_KEY)


def _names(names: Sequence[str]) -> str:
    """Join job names for a sentence: `A`, `A and B`, `A, B and C`."""
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _duration(span: timedelta) -> str:
    minutes = max(1, round(span.total_seconds() / 60))
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    return f"{hours} h" if hours else f"{minutes} min"


def _backlog_output(backlog: LaneBacklog) -> str:
    reason = (
        f"behind {backlog.blocker}"
        if backlog.blocker
        else "and nothing is running in this queue"
    )
    return (
        f"{_names(backlog.waiting)} waiting {_duration(backlog.oldest_wait)}, {reason}."
    )


class SchedulerJobsCheck:
    """Warn about overdue, queued, stuck or failing jobs, including on check failure.

    Always reports one row per condition, never one per job, so the scheduler block
    stays the same size whether or not anything is wrong.
    """

    def __init__(
        self,
        factory: async_sessionmaker[AsyncSession],
        *,
        registry: JobRegistry | None = None,
        schedules: ScheduleSource | None = None,
        evaluator: ScheduleEvaluator | None = None,
    ) -> None:
        self._factory = factory
        self._registry = registry
        self._schedules = schedules
        self._evaluator = evaluator

    async def run(self) -> dict[str, CheckObservation]:
        """Assess job health in a short session; a failure only warns."""
        now = datetime.now(UTC)
        try:
            async with self._factory() as session:
                health = await AssessJobHealth(
                    SqlAlchemyJobRunReader(session),
                    get_access_guard(),
                    self._registry or get_job_catalogue().registry,
                    self._schedules or get_schedule_source(),
                    self._evaluator or CronScheduleEvaluator(),
                ).handle(
                    AssessJobHealthQuery(
                        now=now, timezone=get_server_settings().time_zone.key
                    ),
                    SYSTEM_ACTOR,
                )
        except Exception as error:
            if isinstance(error, DATABASE_OUTAGE_ERRORS):
                logger.warning("job health check failed", error=type(error).__name__)
            else:
                logger.exception("job health check failed")
            return {
                key: CheckObservation(
                    component_type="component",
                    observed_value="unknown",
                    observed_unit="jobs",
                    status=CheckStatus.WARN,
                    time=now,
                    output="Job health could not be checked.",
                )
                for key in ALL_KEYS
            }
        return self._observations(health, now)

    @staticmethod
    def _observations(health: JobHealth, now: datetime) -> dict[str, CheckObservation]:
        def row(count: int, output: str | None) -> CheckObservation:
            return CheckObservation(
                component_type="component",
                observed_value=count,
                observed_unit="jobs",
                status=CheckStatus.WARN if count else CheckStatus.PASS,
                time=now,
                output=output if count else None,
            )

        rows = {
            OVERDUE_KEY: row(
                len(health.overdue),
                f"{_names(health.overdue)} did not start at the scheduled time.",
            ),
            STUCK_KEY: row(
                len(health.stuck),
                f"{_names(health.stuck)} running for longer than expected.",
            ),
            FAILING_KEY: row(
                len(health.failing),
                f"{_names(health.failing)} failed on recent runs.",
            ),
        }
        backlogs = {backlog.lane: backlog for backlog in health.backlogs}
        for lane, key in QUEUE_KEYS.items():
            backlog = backlogs.get(lane)
            rows[key] = row(
                len(backlog.waiting) if backlog else 0,
                _backlog_output(backlog) if backlog else None,
            )
        return {key: rows[key] for key in ALL_KEYS}
