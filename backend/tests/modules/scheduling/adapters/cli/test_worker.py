"""Worker lanes, scheduling, liveness and shutdown use real in-memory use cases."""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest
from structlog.testing import capture_logs

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.cli.catalogue import JobBinding, JobCatalogue
from app.modules.scheduling.adapters.cli.execution import JobExecutor
from app.modules.scheduling.adapters.cli.worker import Worker
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
from app.modules.scheduling.application.claim_job_run import ClaimJobRun
from app.modules.scheduling.application.finish_job_run import FinishJobRun
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
from app.modules.scheduling.application.maintain_worker import MaintainWorker
from app.modules.scheduling.application.tick_schedules import TickSchedules
from app.modules.scheduling.domain.errors import DuplicateJobError, UnknownJobError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
    from app.shared_kernel.actor import Actor

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)


async def until(predicate: Callable[[], bool]) -> None:
    """Wait for an observable state transition with a bounded test deadline."""
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0)


@dataclass
class World:
    """Wire the real application commands to independent in-memory UoWs."""

    store: InMemorySchedulingStore = field(default_factory=InMemorySchedulingStore)
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    now: datetime = NOW

    def worker(
        self,
        catalogue: JobCatalogue,
        *,
        grace: float = 1,
        heartbeat_interval: float = 0.01,
        tick_interval: float = 0.01,
    ) -> Worker:
        """Build a fast worker with real recording and scheduling policy."""
        guard = get_access_guard()

        def uow() -> SchedulingUnitOfWork:
            return create_in_memory_scheduling_uow(self.store)

        executor = JobExecutor(
            lambda: HeartbeatJobRun(uow(), guard),
            lambda: FinishJobRun(uow(), guard),
            CheckJobExecution(InMemorySetupState(), guard),
            InMemoryRestoreGuard(),
            now=lambda: self.now,
            heartbeat_interval=0.01,
        )
        return Worker(
            catalogue,
            lambda: ClaimJobRun(uow(), guard),
            lambda: MaintainWorker(uow(), guard),
            lambda: TickSchedules(
                uow(),
                guard,
                catalogue.registry,
                InMemoryScheduleSource({"x": "* * * * *"}),
                CronScheduleEvaluator(),
            ),
            lambda: FinishJobRun(uow(), guard),
            executor,
            worker_id="worker",
            timezone="UTC",
            now=lambda: self.now,
            tick_interval=tick_interval,
            heartbeat_interval=heartbeat_interval,
            poll_interval=0.001,
            shutdown_grace=grace,
        )


async def test_lanes_execute_independently_as_system() -> None:
    """A waiting heavy job cannot prevent a default-lane job from executing."""
    world = World()
    heavy_started = asyncio.Event()
    release_heavy = asyncio.Event()

    async def heavy(actor: Actor) -> None:
        assert actor is SYSTEM_ACTOR
        heavy_started.set()
        await release_heavy.wait()

    async def normal(actor: Actor) -> None:
        await heavy_started.wait()
        assert actor is SYSTEM_ACTOR
        world.stop.set()
        release_heavy.set()

    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(job_key="heavy", lane=Lane.HEAVY),
                handler=heavy,
            ),
            JobBinding(definition=JobDefinition(job_key="normal"), handler=normal),
        ]
    )
    repos = build_in_memory_scheduling_repos(world.store)
    for key, lane in [("heavy", Lane.HEAVY), ("normal", Lane.DEFAULT)]:
        await repos.queue.enqueue(
            JobRun.create(job_key=key, lane=lane, scheduled_for=NOW)
        )
    await asyncio.wait_for(world.worker(catalogue).run(world.stop), timeout=3)
    assert {run.status for run in world.store.runs.values()} == {RunStatus.SUCCEEDED}


async def test_tick_observes_then_submits_a_future_fire() -> None:
    """The loop uses TickSchedules rather than computing due fires itself."""
    world = World()

    async def handler(actor: Actor) -> None:
        world.stop.set()

    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(job_key="x", schedule_key="x"), handler=handler
            )
        ]
    )
    task = asyncio.create_task(world.worker(catalogue).run(world.stop))
    await until(lambda: "x" in world.store.cursors)
    world.now += timedelta(minutes=1)
    await asyncio.wait_for(task, timeout=3)
    assert len(world.store.runs) == 1
    assert next(iter(world.store.runs.values())).scheduled_for == world.now


async def test_tick_logs_each_submitted_run() -> None:
    """A schedule fire is visible at INFO before any worker claims it."""
    world = World()

    async def handler(actor: Actor) -> None:
        world.stop.set()

    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(job_key="x", schedule_key="x"), handler=handler
            )
        ]
    )
    with capture_logs() as logs:
        task = asyncio.create_task(world.worker(catalogue).run(world.stop))
        await until(lambda: "x" in world.store.cursors)
        world.now += timedelta(minutes=1)
        await asyncio.wait_for(task, timeout=3)
    submitted = [entry for entry in logs if entry["event"] == "scheduled run submitted"]
    assert len(submitted) == 1
    run = next(iter(world.store.runs.values()))
    assert submitted[0]["log_level"] == "info"
    assert submitted[0]["job_key"] == "x"
    assert submitted[0]["run_id"] == str(run.id)
    assert submitted[0]["scheduled_for"] == run.scheduled_for.isoformat()
    assert submitted[0]["status"] == "queued"


async def test_idle_worker_reaps_abandoned_work_and_reports_liveness() -> None:
    """Maintenance runs even when there are no queued jobs to execute."""
    world = World(now=NOW + timedelta(minutes=6))
    repos = build_in_memory_scheduling_repos(world.store)
    stale = await repos.queue.enqueue(JobRun.create(job_key="stale", scheduled_for=NOW))
    await repos.queue.claim([Lane.DEFAULT], "dead", NOW)
    task = asyncio.create_task(world.worker(JobCatalogue([])).run(world.stop))
    await until(lambda: "worker" in world.store.workers)
    world.stop.set()
    await asyncio.wait_for(task, timeout=3)
    assert world.store.get(stale.id).status is RunStatus.ABANDONED
    assert await repos.reader.worker_alive(world.now)


async def test_worker_heartbeats_continue_between_schedule_ticks() -> None:
    """Short heartbeat intervals do not accelerate schedule evaluation."""
    world = World()

    async def handler(actor: Actor) -> None:
        pass

    catalogue = JobCatalogue(
        [
            JobBinding(
                definition=JobDefinition(job_key="x", schedule_key="x"),
                handler=handler,
            )
        ]
    )
    worker = world.worker(catalogue, heartbeat_interval=0.001, tick_interval=3600)
    task = asyncio.create_task(worker.run(world.stop))
    try:
        await until(
            lambda: "x" in world.store.cursors and "worker" in world.store.workers
        )
        world.now = NOW + timedelta(minutes=2)
        await until(lambda: world.store.workers["worker"] == world.now)
        assert world.store.cursors["x"].checked_until == NOW
        assert not world.store.runs
    finally:
        world.stop.set()
        await asyncio.wait_for(task, timeout=3)


async def test_heartbeat_and_tick_activity_is_debug_only() -> None:
    """Routine liveness never reaches the INFO stream."""
    world = World()
    worker = world.worker(JobCatalogue([]), heartbeat_interval=0.001)
    with capture_logs() as logs:
        task = asyncio.create_task(worker.run(world.stop))
        try:
            await until(lambda: "worker" in world.store.workers)
            await asyncio.sleep(0.01)
        finally:
            world.stop.set()
            await asyncio.wait_for(task, timeout=3)
    events = {entry["event"]: entry["log_level"] for entry in logs}
    assert events["worker heartbeat recorded"] == "debug"
    assert events["schedule tick completed"] == "debug"


async def test_shutdown_finishes_current_job_without_claiming_another() -> None:
    """Graceful shutdown stops claims while permitting an active handler to finish."""
    world = World()
    started = asyncio.Event()
    release = asyncio.Event()

    async def handler(actor: Actor) -> None:
        world.stop.set()
        started.set()
        await release.wait()

    catalogue = JobCatalogue(
        [JobBinding(definition=JobDefinition(job_key="x"), handler=handler)]
    )
    repos = build_in_memory_scheduling_repos(world.store)
    first = await repos.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE)
    )
    second = await repos.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE)
    )
    task = asyncio.create_task(world.worker(catalogue).run(world.stop))
    await asyncio.wait_for(started.wait(), timeout=2)
    release.set()
    await asyncio.wait_for(task, timeout=3)
    assert world.store.get(first.id).status is RunStatus.SUCCEEDED
    assert world.store.get(second.id).status is RunStatus.QUEUED


async def test_shutdown_grace_cancels_unfinished_execution_for_reaper() -> None:
    """A job beyond the grace period is cancelled without a false success result."""
    world = World()
    cancelled = asyncio.Event()

    async def handler(actor: Actor) -> None:
        world.stop.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    catalogue = JobCatalogue(
        [JobBinding(definition=JobDefinition(job_key="x"), handler=handler)]
    )
    await build_in_memory_scheduling_repos(world.store).queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW)
    )
    await asyncio.wait_for(
        world.worker(catalogue, grace=0.01).run(world.stop), timeout=3
    )
    assert cancelled.is_set()
    assert next(iter(world.store.runs.values())).status is RunStatus.RUNNING


async def test_unregistered_queued_jobs_are_skipped() -> None:
    """A job removed in a deployment cannot crash or execute arbitrary code."""
    world = World()
    accepted = await build_in_memory_scheduling_repos(world.store).queue.enqueue(
        JobRun.create(job_key="removed", scheduled_for=NOW)
    )
    task = asyncio.create_task(world.worker(JobCatalogue([])).run(world.stop))
    await until(lambda: world.store.get(accepted.id).status is RunStatus.SKIPPED)
    world.stop.set()
    await asyncio.wait_for(task, timeout=3)
    assert world.store.get(accepted.id).error == "unknown_job"


def test_catalogue_rejects_duplicates_and_unknown_handlers() -> None:
    """Handler bindings share the metadata registry's key validation."""

    async def handler(actor: Actor) -> None:
        pass

    binding = JobBinding(definition=JobDefinition(job_key="x"), handler=handler)
    with pytest.raises(DuplicateJobError):
        JobCatalogue([binding, binding])
    with pytest.raises(UnknownJobError):
        JobCatalogue([binding]).handler_for("missing")


async def test_external_cancellation_cleans_up_active_lane_tasks() -> None:
    """Cancelling the worker itself also cancels and awaits its running handler."""
    world = World()
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def handler(actor: Actor) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    catalogue = JobCatalogue(
        [JobBinding(definition=JobDefinition(job_key="x"), handler=handler)]
    )
    await build_in_memory_scheduling_repos(world.store).queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW)
    )
    task = asyncio.create_task(world.worker(catalogue).run(world.stop))
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()


async def test_child_timeout_is_not_misreported_as_shutdown_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Infrastructure timeouts during shutdown must still fail the worker."""
    world = World()

    async def consume(self: Worker, lane: Lane, stop: asyncio.Event) -> None:
        if lane is Lane.DEFAULT:
            stop.set()
            await asyncio.sleep(0.01)
            raise TimeoutError("claim timed out")
        await stop.wait()

    monkeypatch.setattr(Worker, "_consume", consume)
    with pytest.raises(TimeoutError, match="claim timed out"):
        await world.worker(JobCatalogue([])).run(world.stop)
