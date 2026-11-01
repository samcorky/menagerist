"""Schedule observation, catch-up and deployment changes at fixed instants."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from structlog.contextvars import merge_contextvars
from structlog.testing import capture_logs

from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_in_memory_scheduling_repos,
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.application.tick_schedules import (
    TickSchedules,
    TickSchedulesCommand,
)
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import ForbiddenError, ValidationError
from app.shared_kernel.jobs import JobDefinition, MissedRun, Overlap

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

NOW = datetime(2026, 10, 26, 3, tzinfo=UTC)


def use_case(
    store: InMemorySchedulingStore,
    source: InMemoryScheduleSource,
    jobs: list[JobDefinition],
) -> TickSchedules:
    """Wire real cron evaluation and in-memory driven adapters."""
    return TickSchedules(
        create_in_memory_scheduling_uow(store),
        InMemoryAccessGuard(),
        JobRegistry(jobs),
        source,
        CronScheduleEvaluator(),
    )


async def tick(
    store: InMemorySchedulingStore,
    source: InMemoryScheduleSource,
    jobs: list[JobDefinition],
    now: datetime,
    timezone: str = "UTC",
) -> None:
    """Run one guarded tick, as a worker would."""
    await use_case(store, source, jobs).handle(
        TickSchedulesCommand(now=now, timezone=timezone), SYSTEM_ACTOR
    )


async def test_first_observation_does_not_backfill_and_later_ticks_do_not_repeat() -> (
    None
):
    """An explicit cursor permits the first future fire without replaying old ones."""
    store = InMemorySchedulingStore()
    source = InMemoryScheduleSource({"backup.schedule": "0 3 * * *"})
    jobs = [JobDefinition(job_key="backup.create", schedule_key="backup.schedule")]
    repos = build_in_memory_scheduling_repos(store)
    await tick(store, source, jobs, NOW)
    assert await repos.reader.history("backup.create", limit=10) == []
    tomorrow = NOW + timedelta(days=1)
    await tick(store, source, jobs, tomorrow)
    await tick(store, source, jobs, tomorrow)
    runs = await repos.reader.history("backup.create", limit=10)
    assert len(runs) == 1
    assert runs[0].scheduled_for == tomorrow
    assert runs[0].requested_by is None


@pytest.mark.parametrize(
    ("missed", "lateness", "expected"),
    [
        (MissedRun.RUN_ONCE, timedelta(hours=12), 1),
        (MissedRun.RUN_ONCE, timedelta(minutes=1), 0),
        (MissedRun.SKIP, timedelta(hours=12), 0),
    ],
)
async def test_missed_run_policy_and_latest_occurrence(
    missed: MissedRun, lateness: timedelta, expected: int
) -> None:
    """Only the latest eligible fire is submitted after a multi-day outage."""
    store = InMemorySchedulingStore()
    source = InMemoryScheduleSource({"backup.schedule": "0 3 * * *"})
    jobs = [
        JobDefinition(
            job_key="backup.create",
            schedule_key="backup.schedule",
            missed_run=missed,
            max_lateness=lateness,
        )
    ]
    await tick(store, source, jobs, NOW - timedelta(days=7))
    await tick(store, source, jobs, NOW + timedelta(hours=1))
    runs = await build_in_memory_scheduling_repos(store).reader.history(
        "backup.create", limit=10
    )
    assert len(runs) == expected
    if runs:
        assert runs[0].scheduled_for == NOW


async def test_disabled_changed_and_reenabled_schedules_reset_the_cursor() -> None:
    """Disabled periods and deployment changes cannot backfill under a new schedule."""
    store = InMemorySchedulingStore()
    source = InMemoryScheduleSource({"backup.schedule": ""})
    jobs = [
        JobDefinition(
            job_key="backup.create",
            schedule_key="backup.schedule",
            missed_run=MissedRun.RUN_ONCE,
            overlap=Overlap.QUEUE,
        )
    ]
    await tick(store, source, jobs, NOW - timedelta(days=2))
    source.values["backup.schedule"] = "0 3 * * *"
    await tick(store, source, jobs, NOW)
    repos = build_in_memory_scheduling_repos(store)
    assert await repos.reader.history("backup.create", limit=10) == []
    await tick(store, source, jobs, NOW + timedelta(days=1))
    assert len(await repos.reader.history("backup.create", limit=10)) == 1
    source.values["backup.schedule"] = "0 4 * * *"
    await tick(store, source, jobs, NOW + timedelta(days=1, hours=1))
    assert len(await repos.reader.history("backup.create", limit=10)) == 1
    await tick(store, source, jobs, NOW + timedelta(days=2, hours=1))
    assert len(await repos.reader.history("backup.create", limit=10)) == 2
    await tick(store, source, jobs, NOW + timedelta(days=3), timezone="Europe/London")
    assert len(await repos.reader.history("backup.create", limit=10)) == 2


async def test_manual_only_jobs_and_clock_regression() -> None:
    """Manual jobs need no schedule source, and a cursor never moves backwards."""
    store = InMemorySchedulingStore()
    source = InMemoryScheduleSource({"scheduled": "* * * * *"})
    jobs = [
        JobDefinition(job_key="manual"),
        JobDefinition(job_key="scheduled", schedule_key="scheduled"),
    ]
    await tick(store, source, jobs, NOW)
    await tick(store, source, jobs, NOW - timedelta(minutes=1))
    await tick(store, source, jobs, NOW + timedelta(minutes=1))
    repos = build_in_memory_scheduling_repos(store)
    assert len(await repos.reader.history("scheduled", limit=10)) == 1
    assert await repos.reader.history("manual", limit=10) == []


async def test_tick_commits_its_unit_of_work_and_checks_access_first() -> None:
    """Queue submissions and cursor advances share the command's transaction."""
    store = InMemorySchedulingStore()
    uow = create_in_memory_scheduling_uow(store)
    command = TickSchedulesCommand(now=NOW, timezone="UTC")
    tick_case = TickSchedules(
        uow,
        InMemoryAccessGuard(),
        JobRegistry([]),
        InMemoryScheduleSource({}),
        CronScheduleEvaluator(),
    )
    await tick_case.handle(command, SYSTEM_ACTOR)
    assert uow.committed
    denied = create_in_memory_scheduling_uow(store)
    tick_case = TickSchedules(
        denied,
        InMemoryAccessGuard(deny=True),
        JobRegistry([]),
        InMemoryScheduleSource({}),
        CronScheduleEvaluator(),
    )
    with pytest.raises(ForbiddenError):
        await tick_case.handle(command, SYSTEM_ACTOR)
    assert not denied.committed


async def test_no_fire_window_and_zero_lateness_boundary() -> None:
    """Quiet ticks enqueue nothing, while an on-time fire with zero grace is kept."""
    store = InMemorySchedulingStore()
    source = InMemoryScheduleSource({"daily": "0 3 * * *"})
    jobs = [
        JobDefinition(
            job_key="daily",
            schedule_key="daily",
            missed_run=MissedRun.RUN_ONCE,
            max_lateness=timedelta(),
        )
    ]
    await tick(store, source, jobs, NOW)
    await tick(store, source, jobs, NOW + timedelta(minutes=1))
    reader = build_in_memory_scheduling_repos(store).reader
    assert await reader.history("daily", limit=10) == []
    await tick(store, source, jobs, NOW + timedelta(days=1))
    runs = await reader.history("daily", limit=10)
    assert len(runs) == 1
    assert runs[0].scheduled_for == NOW + timedelta(days=1)


async def test_cursor_survives_removed_run_history() -> None:
    """Pruning history cannot make an already observed interval new again."""
    store = InMemorySchedulingStore()
    source = InMemoryScheduleSource({"daily": "0 3 * * *"})
    jobs = [JobDefinition(job_key="daily", schedule_key="daily")]
    await tick(store, source, jobs, NOW)
    await tick(store, source, jobs, NOW + timedelta(days=1))
    store.runs.clear()
    await tick(store, source, jobs, NOW + timedelta(days=1))
    assert not store.runs


def changes(logs: Sequence[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """The schedule-change log lines among captured output."""
    return [line for line in logs if line["event"] == "job schedule changed"]


async def test_a_changed_schedule_is_logged_with_when_it_runs_next() -> None:
    """A first sighting is quiet; an edit logs the old and new schedule and next run."""
    store = InMemorySchedulingStore()
    job = JobDefinition(job_key="backup.create", schedule_key="backup.schedule")
    source = InMemoryScheduleSource({"backup.schedule": "0 3 * * *"})
    with capture_logs(processors=[merge_contextvars]) as first:
        await tick(store, source, [job], NOW)
    assert changes(first) == []

    source.values["backup.schedule"] = "0 4 * * *"
    with capture_logs(processors=[merge_contextvars]) as second:
        await tick(store, source, [job], NOW + timedelta(minutes=1))
    (line,) = changes(second)
    assert line["job_key"] == "backup.create"
    assert (line["previous_schedule"], line["schedule"]) == ("0 3 * * *", "0 4 * * *")
    assert (line["previous_timezone"], line["timezone"]) == ("UTC", "UTC")
    assert line["next_run"] == "2026-10-26T04:00:00+00:00"
    assert line["log_level"] == "info"

    with capture_logs(processors=[merge_contextvars]) as third:
        await tick(store, source, [job], NOW + timedelta(minutes=2))
    assert changes(third) == []


async def test_turning_a_schedule_off_and_changing_the_zone_are_logged() -> None:
    """An empty schedule has no next run; a new instance zone is a change too."""
    store = InMemorySchedulingStore()
    job = JobDefinition(job_key="backup.create", schedule_key="backup.schedule")
    source = InMemoryScheduleSource({"backup.schedule": "0 3 * * *"})
    await tick(store, source, [job], NOW)

    source.values["backup.schedule"] = ""
    with capture_logs(processors=[merge_contextvars]) as off:
        await tick(store, source, [job], NOW + timedelta(minutes=1))
    (line,) = changes(off)
    assert (line["schedule"], line["next_run"]) == (None, None)
    assert line["previous_schedule"] == "0 3 * * *"

    source.values["backup.schedule"] = "0 3 * * *"
    await tick(store, source, [job], NOW + timedelta(minutes=2))
    with capture_logs(processors=[merge_contextvars]) as zone:
        await tick(
            store, source, [job], NOW + timedelta(minutes=3), timezone="Asia/Tokyo"
        )
    (line,) = changes(zone)
    assert (line["previous_timezone"], line["timezone"]) == ("UTC", "Asia/Tokyo")
    assert line["next_run"] == "2026-10-26T18:00:00+00:00"  # 03:00 in Tokyo


async def test_an_unreadable_schedule_is_logged_without_a_next_run() -> None:
    """A change is still reported when the evaluator cannot say when it next runs."""

    class Refuses:
        async def next_fire(
            self, expression: str, timezone: str, *, after: datetime
        ) -> datetime | None:
            raise ValidationError("Invalid cron schedule")

        async def latest_fire(
            self, expression: str, timezone: str, *, after: datetime, until: datetime
        ) -> datetime | None:
            return None

    store = InMemorySchedulingStore()
    job = JobDefinition(job_key="backup.create", schedule_key="backup.schedule")
    source = InMemoryScheduleSource({"backup.schedule": "0 3 * * *"})
    uow = create_in_memory_scheduling_uow(store)
    guard = InMemoryAccessGuard()
    registry = JobRegistry([job])

    async def run(now: datetime) -> None:
        await TickSchedules(uow, guard, registry, source, Refuses()).handle(
            TickSchedulesCommand(now=now, timezone="UTC"), SYSTEM_ACTOR
        )

    await run(NOW)
    source.values["backup.schedule"] = "nonsense"
    with capture_logs(processors=[merge_contextvars]) as logs:
        await run(NOW + timedelta(minutes=1))
    (line,) = changes(logs)
    assert (line["schedule"], line["next_run"]) == ("nonsense", None)
