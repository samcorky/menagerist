"""Overdue, stuck and repeatedly failing jobs are found from run history."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.in_memory_job_run_reader import (
    InMemoryJobRunReader,
)
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_evaluator import (
    InMemoryScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.application.assess_job_health import (
    AssessJobHealth,
    AssessJobHealthQuery,
    JobHealth,
)
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.jobs import JobDefinition, Lane

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)
# max_lateness (10 min) plus the default grace (5 min).
DUE_BY = NOW - timedelta(minutes=15)
FIRE = datetime(2026, 10, 27, 3, tzinfo=UTC)

BACKUP = JobDefinition(job_key="backup", schedule_key="backup.cron", title="Backup")
PURGE = JobDefinition(job_key="purge", schedule_key="purge.cron")
MANUAL = JobDefinition(job_key="manual")


class Fixture:
    """An in-memory scheduler with a daily 03:00 job, plus helpers to seed runs."""

    def __init__(
        self,
        *definitions: JobDefinition,
        fires: list[datetime] | None = None,
    ) -> None:
        self.store = InMemorySchedulingStore()
        self.use_case = AssessJobHealth(
            InMemoryJobRunReader(self.store),
            get_access_guard(),
            JobRegistry(definitions or (BACKUP,)),
            InMemoryScheduleSource({"backup.cron": "0 3 * * *", "purge.cron": ""}),
            InMemoryScheduleEvaluator({"0 3 * * *": fires or [FIRE]}),
        )

    def add(
        self,
        job_key: str = "backup",
        *,
        status: RunStatus = RunStatus.SUCCEEDED,
        scheduled_for: datetime = FIRE,
        age: timedelta = timedelta(hours=1),
        scheduled: bool = True,
        started_at: datetime | None = None,
    ) -> JobRun:
        """Store a run created `age` before NOW."""
        run = JobRun.create(
            job_key=job_key,
            scheduled_for=scheduled_for,
            deduplication_key=uuid7() if scheduled else None,
        )
        run.created_at = NOW - age
        run.status = status
        run.started_at = started_at
        self.store.save(run)
        return run

    async def assess(self) -> JobHealth:
        """Assess every registered job at NOW."""
        return await self.use_case.handle(
            AssessJobHealthQuery(now=NOW, timezone="UTC"), SYSTEM_ACTOR
        )


async def test_healthy_jobs_report_nothing() -> None:
    """A job that ran at its last fire is not flagged."""
    fixture = Fixture()
    fixture.add()
    assert await fixture.assess() == JobHealth()


async def test_queued_run_past_its_window_is_a_lane_backlog() -> None:
    """Work waiting longer than lateness plus grace is queue pressure, not overdue."""
    fixture = Fixture()
    fixture.add(status=RunStatus.QUEUED, scheduled_for=DUE_BY)
    health = await fixture.assess()
    assert health.overdue == ()
    (backlog,) = health.backlogs
    assert backlog.lane is Lane.DEFAULT
    assert backlog.waiting == ("Backup",)
    assert backlog.oldest_wait == timedelta(minutes=15)
    assert backlog.blocker is None


async def test_queued_run_inside_its_window_is_not_a_backlog() -> None:
    """Work that is merely waiting its turn is fine."""
    fixture = Fixture()
    fixture.add(status=RunStatus.QUEUED, scheduled_for=DUE_BY + timedelta(seconds=1))
    assert (await fixture.assess()).backlogs == ()


async def test_backlog_names_what_is_holding_the_lane() -> None:
    """A lane has one slot, so the running job in it is the blocker."""
    heavy = JobDefinition(job_key="big", lane=Lane.HEAVY, title="Big job")
    waiting = JobDefinition(job_key="late", lane=Lane.HEAVY, title="Late job")
    other = JobDefinition(job_key="quick", title="Quick")
    fixture = Fixture(heavy, waiting, other)
    fixture.add("big", status=RunStatus.RUNNING, started_at=NOW, age=timedelta(hours=3))
    fixture.add("late", status=RunStatus.QUEUED, scheduled_for=NOW - timedelta(hours=3))
    fixture.add("quick", status=RunStatus.RUNNING, started_at=NOW)
    (backlog,) = (await fixture.assess()).backlogs
    assert backlog.lane is Lane.HEAVY
    assert backlog.waiting == ("Late job",)
    assert backlog.oldest_wait == timedelta(hours=3)
    assert backlog.blocker == "Big job"


async def test_backlog_behind_the_same_job_is_found() -> None:
    """A queued run hidden behind a running run of its own job still counts."""
    fixture = Fixture()
    fixture.add(status=RunStatus.RUNNING, age=timedelta(minutes=30), started_at=NOW)
    fixture.add(status=RunStatus.QUEUED, scheduled_for=DUE_BY, age=timedelta(hours=2))
    (backlog,) = (await fixture.assess()).backlogs
    assert backlog.blocker == "Backup"


async def test_each_lane_with_a_backlog_is_reported_separately() -> None:
    """Default and heavy lanes are independent capacity."""
    fixture = Fixture(
        JobDefinition(job_key="a"), JobDefinition(job_key="b", lane=Lane.HEAVY)
    )
    fixture.add("a", status=RunStatus.QUEUED, scheduled_for=DUE_BY)
    fixture.add("b", status=RunStatus.QUEUED, scheduled_for=DUE_BY)
    lanes = [backlog.lane for backlog in (await fixture.assess()).backlogs]
    assert lanes == [Lane.DEFAULT, Lane.HEAVY]


async def test_missed_occurrence_is_overdue() -> None:
    """The scheduler never submitted the latest fire that was due."""
    fixture = Fixture()
    fixture.add(scheduled_for=FIRE - timedelta(days=1))
    assert (await fixture.assess()).overdue == ("Backup",)


async def test_manual_runs_do_not_hide_a_missed_occurrence() -> None:
    """Only scheduled submissions count towards the watermark."""
    fixture = Fixture()
    fixture.add(scheduled_for=FIRE - timedelta(days=1))
    fixture.add(scheduled_for=FIRE, scheduled=False)
    assert (await fixture.assess()).overdue == ("Backup",)


async def test_fire_inside_the_window_is_not_yet_overdue() -> None:
    """A fire younger than lateness plus grace gets time to be submitted."""
    fixture = Fixture(fires=[NOW - timedelta(minutes=14)])
    fixture.add(scheduled_for=FIRE - timedelta(days=1))
    assert (await fixture.assess()).overdue == ()


async def test_job_that_never_ran_is_not_flagged_overdue() -> None:
    """A fresh install cannot be told apart from a scheduler fault."""
    assert (await Fixture().assess()).overdue == ()


@pytest.mark.parametrize("definition", [PURGE, MANUAL])
async def test_unscheduled_or_switched_off_jobs_are_never_overdue(
    definition: JobDefinition,
) -> None:
    """Without an expression there is nothing to be late for."""
    fixture = Fixture(definition)
    fixture.add(definition.job_key, scheduled_for=FIRE - timedelta(days=3))
    assert (await fixture.assess()).overdue == ()


async def test_running_past_the_threshold_is_stuck() -> None:
    """The threshold comes from the job definition."""
    fixture = Fixture()
    fixture.add(
        status=RunStatus.RUNNING, started_at=NOW - timedelta(hours=1, seconds=1)
    )
    assert (await fixture.assess()).stuck == ("Backup",)


async def test_running_within_the_threshold_is_not_stuck() -> None:
    """A long but normal run is left alone."""
    fixture = Fixture()
    fixture.add(status=RunStatus.RUNNING, started_at=NOW - timedelta(hours=1))
    assert (await fixture.assess()).stuck == ()


async def test_a_job_may_declare_a_longer_stuck_threshold() -> None:
    """Heavy jobs override the default."""
    slow = JobDefinition(job_key="slow", stuck_after=timedelta(hours=6))
    fixture = Fixture(slow)
    fixture.add("slow", status=RunStatus.RUNNING, started_at=NOW - timedelta(hours=5))
    assert (await fixture.assess()).stuck == ()


async def test_consecutive_failures_are_flagged() -> None:
    """Three failed or abandoned runs in a row make a failing job."""
    fixture = Fixture()
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=1))
    fixture.add(status=RunStatus.ABANDONED, age=timedelta(hours=2))
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=3))
    assert (await fixture.assess()).failing == ("Backup",)


async def test_a_success_breaks_the_streak() -> None:
    """Only an unbroken run of failures counts."""
    fixture = Fixture()
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=1))
    fixture.add(status=RunStatus.SUCCEEDED, age=timedelta(hours=2))
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=3))
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=4))
    assert (await fixture.assess()).failing == ()


async def test_too_few_runs_are_not_a_streak() -> None:
    """Two failures do not reach the default streak of three."""
    fixture = Fixture()
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=1))
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=2))
    assert (await fixture.assess()).failing == ()


async def test_skipped_and_in_flight_runs_are_ignored_for_failures() -> None:
    """A skipped run or the current attempt neither extends nor breaks a streak."""
    fixture = Fixture(JobDefinition(job_key="backup", failure_streak=2))
    fixture.add(status=RunStatus.RUNNING, age=timedelta(minutes=5), started_at=NOW)
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=1))
    fixture.add(status=RunStatus.SKIPPED, age=timedelta(hours=2))
    fixture.add(status=RunStatus.FAILED, age=timedelta(hours=3))
    assert (await fixture.assess()).failing == ("backup",)


async def test_each_condition_lists_every_affected_job_by_name() -> None:
    """Titles are preferred and the job key is the fallback."""
    fixture = Fixture(BACKUP, JobDefinition(job_key="plain"), MANUAL)
    for key in ("backup", "plain"):
        for hours in (1, 2, 3):
            fixture.add(key, status=RunStatus.FAILED, age=timedelta(hours=hours))
    assert (await fixture.assess()).failing == ("Backup", "plain")


async def test_only_the_system_actor_may_ask() -> None:
    """The readiness boundary owns this query."""
    with pytest.raises(ForbiddenError):
        await Fixture().use_case.handle(
            AssessJobHealthQuery(now=NOW, timezone="UTC"), Actor(id=uuid7())
        )
