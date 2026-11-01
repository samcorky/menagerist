"""Execution boundaries, ownership, heartbeats and cancellation."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
import structlog
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.cli.execution import JobExecutor
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
from app.modules.scheduling.adapters.platform.in_memory_restore_guard import (
    InMemoryRestoreGuard,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.adapters.platform.in_memory_setup_state import (
    InMemorySetupState,
)
from app.modules.scheduling.application.check_job_execution import CheckJobExecution
from app.modules.scheduling.application.finish_job_run import FinishJobRun
from app.modules.scheduling.application.get_job_next_run import GetJobNextRun
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
from app.modules.scheduling.domain.errors import LostClaimError, UnknownRunError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import JobDefinition, Lane

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
    from app.shared_kernel.actor import Actor

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


@dataclass
class Harness:
    """Real in-memory persistence and observable transaction commits."""

    store: InMemorySchedulingStore = field(default_factory=InMemorySchedulingStore)
    setup: InMemorySetupState = field(default_factory=InMemorySetupState)
    restore: InMemoryRestoreGuard = field(default_factory=InMemoryRestoreGuard)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    now: datetime = NOW

    def uow(self) -> SchedulingUnitOfWork:
        """Build a transaction that reports its successful commit."""
        uow = create_in_memory_scheduling_uow(self.store)

        async def notify() -> None:
            self.changed.set()

        uow.on_commit(notify)
        return uow

    def executor(
        self, next_run: Callable[[], GetJobNextRun] | None = None
    ) -> JobExecutor:
        """Wire application commands and the eligibility query into the driver."""
        return JobExecutor(
            lambda: HeartbeatJobRun(self.uow(), get_access_guard()),
            lambda: FinishJobRun(self.uow(), get_access_guard()),
            CheckJobExecution(self.setup, get_access_guard()),
            self.restore,
            now=lambda: self.now,
            heartbeat_interval=0.01,
            next_run=next_run,
        )

    async def claimed(self) -> JobRun:
        """Seed one owned execution through the queue contract."""
        repos = build_in_memory_scheduling_repos(self.store)
        await repos.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
        run = await repos.queue.claim([Lane.DEFAULT], "worker", NOW)
        assert run is not None
        return run


async def test_handler_runs_as_system_inside_guard_and_records_success() -> None:
    """The restore guard covers handler execution and the final result commit."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        assert actor is SYSTEM_ACTOR
        assert harness.restore.holders == 1
        harness.now += timedelta(seconds=1)

    await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    stored = harness.store.get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    assert stored.finished_at == harness.now
    assert harness.restore.holders == 0
    assert await build_in_memory_scheduling_repos(harness.store).reader.worker_alive(
        NOW
    )


@pytest.mark.parametrize(
    ("setup", "restore", "reason"),
    [
        (False, True, "setup_incomplete"),
        (True, False, "restore_in_progress"),
        (False, False, "restore_in_progress"),
    ],
)
async def test_blocked_jobs_are_skipped_without_invoking_handler(
    setup: bool, restore: bool, reason: str
) -> None:
    """Both first-run setup and restore block jobs before their handler starts."""
    harness = Harness()
    harness.setup.complete = setup
    harness.restore.available = restore
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        pytest.fail("A blocked handler must not execute")

    await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    stored = harness.store.get(run.id)
    assert stored.status is RunStatus.SKIPPED
    assert stored.error == reason
    assert harness.restore.holders == 0


async def test_setup_independent_jobs_can_execute_before_setup() -> None:
    """Jobs explicitly exempt from setup still honour the restore guard."""
    harness = Harness()
    harness.setup.complete = False
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        assert actor is SYSTEM_ACTOR

    await harness.executor().execute(
        run, JobDefinition(job_key="x", needs_setup_complete=False), handler
    )
    assert harness.store.get(run.id).status is RunStatus.SUCCEEDED


async def test_handler_failure_is_recorded_and_guard_is_released() -> None:
    """A handler exception becomes a failed run rather than crashing the worker."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        raise ValueError("job failed")

    await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    stored = harness.store.get(run.id)
    assert stored.status is RunStatus.FAILED
    assert stored.error == "ValueError('job failed')"
    assert harness.restore.holders == 0


async def test_long_running_handler_renews_run_and_worker_heartbeats() -> None:
    """Heartbeat commits use independent short transactions during execution."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        harness.changed.clear()
        harness.now += timedelta(minutes=1)
        await asyncio.wait_for(harness.changed.wait(), timeout=2)
        assert harness.store.get(run.id).heartbeat_at == harness.now
        assert harness.store.workers["worker"] == harness.now
        assert harness.restore.holders == 1

    await asyncio.wait_for(
        harness.executor().execute(run, JobDefinition(job_key="x"), handler), timeout=3
    )
    assert harness.store.get(run.id).status is RunStatus.SUCCEEDED


async def test_lost_claim_cancels_handler_and_preserves_abandonment() -> None:
    """Heartbeat ownership failures stop work instead of writing a stale result."""
    harness = Harness()
    run = await harness.claimed()
    cancelled = asyncio.Event()

    async def handler(actor: Actor) -> None:
        repos = build_in_memory_scheduling_repos(harness.store)
        await repos.recorder.reap_abandoned(
            NOW + timedelta(minutes=1), NOW + timedelta(minutes=2)
        )
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(LostClaimError):
        await asyncio.wait_for(
            harness.executor().execute(run, JobDefinition(job_key="x"), handler),
            timeout=3,
        )
    assert cancelled.is_set()
    assert harness.store.get(run.id).status is RunStatus.ABANDONED
    assert harness.restore.holders == 0


async def test_cancellation_releases_guard_and_leaves_run_for_reaper() -> None:
    """Shutdown cancellation is not reported as successful execution."""
    harness = Harness()
    run = await harness.claimed()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(actor: Actor) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(
        harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    )
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert harness.store.get(run.id).status is RunStatus.RUNNING
    assert harness.restore.holders == 0


@pytest.mark.parametrize("missing", [False, True])
async def test_stale_claim_cannot_start_a_handler(missing: bool) -> None:
    """The first heartbeat checks current persisted ownership before invocation."""
    harness = Harness()
    run = await harness.claimed()
    if missing:
        harness.store.runs.clear()
    else:
        await build_in_memory_scheduling_repos(harness.store).recorder.finish(
            run.id, "worker", RunStatus.SUCCEEDED, NOW
        )

    async def handler(actor: Actor) -> None:
        pytest.fail("A stale claimant must not execute")

    with pytest.raises(UnknownRunError if missing else LostClaimError):
        await harness.executor().execute(run, JobDefinition(job_key="x"), handler)


async def test_unclaimed_run_is_rejected() -> None:
    """An executor cannot start work that has not passed through claim."""
    harness = Harness()
    run = JobRun.create(job_key="x", scheduled_for=NOW)

    async def handler(actor: Actor) -> None:
        pytest.fail("An unclaimed run must not execute")

    with pytest.raises(LostClaimError):
        await harness.executor().execute(run, JobDefinition(job_key="x"), handler)


async def test_successful_job_logs_start_and_outcome_with_context() -> None:
    """Lifecycle logs carry identity and a monotonic duration without leaking."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        return None

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await harness.executor().execute(
            run, JobDefinition(job_key="x", lane=Lane.DEFAULT), handler
        )
    started, finished = logs
    assert started["event"] == "job started"
    assert started["log_level"] == "info"
    assert finished["event"] == "job finished"
    assert finished["log_level"] == "info"
    assert finished["status"] == "succeeded"
    assert isinstance(finished["duration_seconds"], float)
    for entry in logs:
        assert entry["job_key"] == "x"
        assert entry["run_id"] == str(run.id)
        assert entry["lane"] == "default"
        assert entry["worker_id"] == "worker"
    assert structlog.contextvars.get_contextvars() == {}


async def test_skipped_and_failed_jobs_log_their_outcome() -> None:
    """Skips keep their reason and failures keep the traceback log."""
    harness = Harness()
    harness.setup.complete = False
    skipped = await harness.claimed()

    async def handler(actor: Actor) -> None:
        raise ValueError("job failed")

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await harness.executor().execute(skipped, JobDefinition(job_key="x"), handler)
    assert logs[-1]["event"] == "job skipped"
    assert logs[-1]["reason"] == "setup_incomplete"

    harness = Harness()
    failed = await harness.claimed()
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await harness.executor().execute(failed, JobDefinition(job_key="x"), handler)
    assert [entry["event"] for entry in logs] == [
        "job started",
        "scheduled job failed",
        "job finished",
    ]
    assert logs[1]["exc_info"] is True
    assert logs[2]["status"] == "failed"
    assert logs[2]["log_level"] == "warning"


async def test_cancelled_and_lost_claims_are_not_logged_as_finished() -> None:
    """Only recorded outcomes use the finished event."""
    harness = Harness()
    run = await harness.claimed()
    started = asyncio.Event()

    async def handler(actor: Actor) -> None:
        started.set()
        await asyncio.Event().wait()

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        task = asyncio.create_task(
            harness.executor().execute(run, JobDefinition(job_key="x"), handler)
        )
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert [entry["event"] for entry in logs] == ["job started", "job cancelled"]
    assert logs[-1]["log_level"] == "warning"
    assert "duration_seconds" in logs[-1]

    harness = Harness()
    run = await harness.claimed()
    await build_in_memory_scheduling_repos(harness.store).recorder.finish(
        run.id, "worker", RunStatus.SUCCEEDED, NOW
    )
    with (
        capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs,
        pytest.raises(LostClaimError),
    ):
        await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    assert "job finished" not in [entry["event"] for entry in logs]
    assert logs[-1]["event"] == "job claim lost"


async def test_concurrent_jobs_keep_isolated_log_context() -> None:
    """Each lane task binds its own identity."""
    harness = Harness()
    first = await harness.claimed()
    repos = build_in_memory_scheduling_repos(harness.store)
    await repos.queue.enqueue(JobRun.create(job_key="y", scheduled_for=NOW))
    second = await repos.queue.claim([Lane.DEFAULT], "worker", NOW)
    assert second is not None
    gate = asyncio.Event()

    async def handler(actor: Actor) -> None:
        await gate.wait()

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        tasks = [
            asyncio.create_task(
                harness.executor().execute(run, JobDefinition(job_key=key), handler)
            )
            for run, key in ((first, "x"), (second, "y"))
        ]
        await asyncio.sleep(0.05)
        gate.set()
        await asyncio.gather(*tasks)
    for entry in logs:
        expected = first if entry["job_key"] == "x" else second
        assert entry["run_id"] == str(expected.id)


async def test_finished_and_skipped_jobs_log_their_next_scheduled_time() -> None:
    """Outcome lines say when the job fires next; a broken lookup cannot hide them."""
    definition = JobDefinition(job_key="x", schedule_key="x.cron")
    registry = JobRegistry([definition])
    guard = get_access_guard()

    def lookup() -> GetJobNextRun:
        source = InMemoryScheduleSource({"x.cron": "0 15 * * *"})
        return GetJobNextRun(registry, source, CronScheduleEvaluator(), guard)

    def broken() -> GetJobNextRun:
        source = InMemoryScheduleSource({})
        return GetJobNextRun(registry, source, CronScheduleEvaluator(), guard)

    async def handler(actor: Actor) -> None:
        return None

    upcoming = datetime(2026, 10, 26, 15, tzinfo=UTC).isoformat()
    for factory, expected in ((lookup, upcoming), (broken, None)):
        harness = Harness()
        run = await harness.claimed()
        with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
            await harness.executor(factory).execute(run, definition, handler)
        finished = next(entry for entry in logs if entry["event"] == "job finished")
        assert finished["next_run_at"] == expected
        assert harness.store.get(run.id).status is RunStatus.SUCCEEDED

    harness = Harness()
    harness.setup.complete = False
    run = await harness.claimed()
    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await harness.executor(lookup).execute(run, definition, handler)
    assert logs[-1]["event"] == "job skipped"
    assert logs[-1]["next_run_at"] == upcoming


async def test_next_scheduled_time_is_absent_without_a_lookup() -> None:
    """Run-now and unscheduled executors still log a null next run."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor) -> None:
        return None

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    assert logs[-1]["next_run_at"] is None
