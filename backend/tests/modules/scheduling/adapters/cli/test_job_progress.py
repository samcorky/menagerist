"""The executor hands each handler a reporter that writes to the run's row."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.cli.execution import JobExecutor
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_in_memory_scheduling_repos,
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.in_memory_restore_guard import (
    InMemoryRestoreGuard,
)
from app.modules.scheduling.adapters.platform.in_memory_setup_state import (
    InMemorySetupState,
)
from app.modules.scheduling.application.check_job_execution import CheckJobExecution
from app.modules.scheduling.application.finish_job_run import FinishJobRun
from app.modules.scheduling.application.heartbeat_job_run import HeartbeatJobRun
from app.modules.scheduling.application.record_job_run_progress import (
    RecordJobRunProgress,
    RecordJobRunProgressCommand,
)
from app.modules.scheduling.domain.errors import LostClaimError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.errors import NotFoundError
from app.shared_kernel.jobs import JobDefinition, Lane
from app.shared_kernel.progress import (
    GENERIC_FAILURE,
    NULL_PROGRESS,
    Phase,
    ProgressSnapshot,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from app.shared_kernel.actor import Actor
    from app.shared_kernel.progress import ProgressReporter

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
PLAN = (
    Phase(key="database", label="Saving your collection", weight=3),
    Phase(key="media", label="Saving photos and files", weight=5),
)


@dataclass
class Harness:
    """Real in-memory persistence behind an executor that records progress."""

    store: InMemorySchedulingStore = field(default_factory=InMemorySchedulingStore)
    setup: InMemorySetupState = field(default_factory=InMemorySetupState)
    restore: InMemoryRestoreGuard = field(default_factory=InMemoryRestoreGuard)

    def executor(
        self,
        *,
        record_progress: bool = True,
        recorder: Callable[[], RecordJobRunProgress] | None = None,
    ) -> JobExecutor:
        """Wire the executor, with the real recorder, a given one, or none."""
        guard = get_access_guard()
        return JobExecutor(
            lambda: HeartbeatJobRun(create_in_memory_scheduling_uow(self.store), guard),
            lambda: FinishJobRun(create_in_memory_scheduling_uow(self.store), guard),
            CheckJobExecution(self.setup, guard),
            self.restore,
            now=lambda: NOW,
            heartbeat_interval=60,
            record_progress=recorder
            or (
                (
                    lambda: RecordJobRunProgress(
                        create_in_memory_scheduling_uow(self.store), guard
                    )
                )
                if record_progress
                else None
            ),
        )

    async def claimed(self) -> JobRun:
        """Seed one owned execution through the queue contract."""
        repos = build_in_memory_scheduling_repos(self.store)
        await repos.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
        run = await repos.queue.claim([Lane.DEFAULT], "worker", NOW)
        assert run is not None
        return run


async def test_the_handler_sees_its_progress_on_the_run_row() -> None:
    """Phase changes are written as they happen, and a success clears them."""
    harness = Harness()
    run = await harness.claimed()
    seen: list[tuple[int, str]] = []

    async def handler(actor: Actor, progress: ProgressReporter) -> None:
        await progress.begin(PLAN)
        await progress.start("database")
        await progress.start("media", 4)
        snapshot = harness.store.get(run.id).progress
        assert snapshot is not None
        seen.append((snapshot.percent, snapshot.phases[1].state))

    await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    assert seen == [(37, "running")]
    stored = harness.store.get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    assert stored.progress is None


async def test_a_failed_job_keeps_where_it_stopped() -> None:
    """The failure is recorded on the snapshot, with curated wording only."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor, progress: ProgressReporter) -> None:
        await progress.begin(PLAN)
        await progress.start("media", 4)
        await progress.advance(3)
        raise OSError("/data/media/secret: permission denied")

    await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    stored = harness.store.get(run.id)
    assert stored.status is RunStatus.FAILED
    assert stored.progress is not None
    assert stored.progress.outcome == "failed"
    assert stored.progress.message == GENERIC_FAILURE
    assert (stored.progress.phases[1].done, stored.progress.phases[1].total) == (3, 4)


async def test_a_domain_error_message_is_kept_as_written() -> None:
    """A domain error is already written for people."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor, progress: ProgressReporter) -> None:
        await progress.begin(PLAN)
        raise NotFoundError("The backup went missing.")

    await harness.executor().execute(run, JobDefinition(job_key="x"), handler)
    progress = harness.store.get(run.id).progress
    assert progress is not None
    assert progress.message == "The backup went missing."


async def test_without_a_recorder_the_handler_gets_a_null_reporter() -> None:
    """An executor wired without progress still runs every handler."""
    harness = Harness()
    run = await harness.claimed()

    async def handler(actor: Actor, progress: ProgressReporter) -> None:
        assert progress is NULL_PROGRESS

    await harness.executor(record_progress=False).execute(
        run, JobDefinition(job_key="x"), handler
    )
    assert harness.store.get(run.id).status is RunStatus.SUCCEEDED


async def test_a_failing_progress_write_never_fails_the_job() -> None:
    """If the row cannot be written the job still succeeds."""
    harness = Harness()
    run = await harness.claimed()

    def broken() -> RecordJobRunProgress:
        raise RuntimeError("database unavailable")

    executor = harness.executor(recorder=broken)

    async def handler(actor: Actor, progress: ProgressReporter) -> None:
        await progress.begin(PLAN)
        await progress.start("media", 4)

    await executor.execute(run, JobDefinition(job_key="x"), handler)
    assert harness.store.get(run.id).status is RunStatus.SUCCEEDED


async def test_a_late_write_after_the_run_finished_is_refused() -> None:
    """The use case, like a heartbeat, refuses a worker that no longer owns the run."""
    harness = Harness()
    run = await harness.claimed()
    repos = build_in_memory_scheduling_repos(harness.store)
    await repos.recorder.finish(run.id, "worker", RunStatus.SUCCEEDED, NOW)
    use_case = RecordJobRunProgress(
        create_in_memory_scheduling_uow(harness.store), get_access_guard()
    )
    with pytest.raises(LostClaimError):
        await use_case.handle(
            RecordJobRunProgressCommand(
                run_id=run.id,
                worker_id="worker",
                snapshot=ProgressSnapshot(
                    phases=(), message=None, percent=0, outcome="running"
                ),
            ),
            SYSTEM_ACTOR,
        )
