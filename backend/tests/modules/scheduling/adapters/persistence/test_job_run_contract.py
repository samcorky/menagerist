"""Queue contracts shared with the future Postgres adapter."""

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest

from app.modules.scheduling.adapters.persistence.in_memory_job_run_queue import (
    InMemoryJobRunQueue,
)
from app.modules.scheduling.adapters.persistence.in_memory_job_run_reader import (
    InMemoryJobRunReader,
)
from app.modules.scheduling.adapters.persistence.in_memory_job_run_recorder import (
    InMemoryJobRunRecorder,
)
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.domain.errors import LostClaimError, UnknownRunError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.modules.scheduling.ports.job_run_queue import JobRunQueue
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.modules.scheduling.ports.job_run_recorder import JobRunRecorder
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap


def run_id(run: JobRun | None) -> UUID:
    """Assert that a port returned a run before inspecting its identifier."""
    assert run is not None
    return run.id


NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


@dataclass(kw_only=True)
class QueueHarness:
    """The contract exposes ports so another adapter can use the same tests."""

    queue: JobRunQueue
    reader: JobRunReader
    recorder: JobRunRecorder


@pytest.fixture
def harness() -> QueueHarness:
    """Wire all three adapters to the same in-memory store."""
    store = InMemorySchedulingStore()
    return QueueHarness(
        queue=InMemoryJobRunQueue(store),
        reader=InMemoryJobRunReader(store),
        recorder=InMemoryJobRunRecorder(store),
    )


@pytest.mark.parametrize("policy", [Overlap.SKIP, Overlap.COALESCE, Overlap.QUEUE])
async def test_accepted_runs_and_scheduled_occurrences_are_idempotent(
    harness: QueueHarness, policy: Overlap
) -> None:
    """Retrying an accepted id or fire time cannot create another execution."""
    job = JobDefinition(job_key="x", overlap=policy)
    first = JobRun.for_schedule(job, NOW)
    accepted = await harness.queue.enqueue(first)
    assert (await harness.queue.enqueue(first)).id == accepted.id
    assert (
        await harness.queue.enqueue(JobRun.for_schedule(job, NOW))
    ).id == accepted.id
    await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    await harness.recorder.finish(accepted.id, "worker", RunStatus.SUCCEEDED, NOW)
    assert (
        await harness.queue.enqueue(JobRun.for_schedule(job, NOW))
    ).id == accepted.id
    assert len(await harness.reader.history("x", limit=100)) == 1


@pytest.mark.parametrize("policy", [Overlap.SKIP, Overlap.COALESCE, Overlap.QUEUE])
async def test_overlap_and_serial_execution(
    harness: QueueHarness, policy: Overlap
) -> None:
    """Skip drops overlap, coalesce keeps one waiter, queue retains all waiters."""
    first = await harness.queue.enqueue(
        JobRun(job_key="x", scheduled_for=NOW, overlap=policy)
    )
    await harness.queue.claim([Lane.DEFAULT], "first", NOW)
    second = await harness.queue.enqueue(
        JobRun(job_key="x", scheduled_for=NOW, overlap=policy)
    )
    third = await harness.queue.enqueue(
        JobRun(job_key="x", scheduled_for=NOW, overlap=policy)
    )
    assert await harness.queue.claim([Lane.DEFAULT], "other", NOW) is None
    if policy is Overlap.SKIP:
        assert second.id == third.id == first.id
        expected = 1
    elif policy is Overlap.COALESCE:
        assert first.id != second.id
        assert second.id == third.id
        expected = 2
    else:
        assert len({first.id, second.id, third.id}) == 3
        expected = 3
    await harness.recorder.finish(first.id, "first", RunStatus.SUCCEEDED, NOW)
    claimed = await harness.queue.claim([Lane.DEFAULT], "other", NOW)
    assert (claimed is None) == (policy is Overlap.SKIP)
    assert len(await harness.reader.history("x", limit=100)) == expected


async def test_run_now_reuses_active_work_even_for_queue_policy(
    harness: QueueHarness,
) -> None:
    """Repeated manual requests return the active run instead of stacking it."""
    first = await harness.queue.enqueue(
        JobRun(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE),
        deduplicate_active=True,
    )
    repeated = await harness.queue.enqueue(
        JobRun(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE),
        deduplicate_active=True,
    )
    assert repeated.id == first.id


async def test_lanes_due_times_and_two_workers(harness: QueueHarness) -> None:
    """A busy heavy job cannot block a due default job or be claimed twice."""
    heavy = await harness.queue.enqueue(
        JobRun(job_key="heavy", scheduled_for=NOW, lane=Lane.HEAVY)
    )
    normal = await harness.queue.enqueue(JobRun(job_key="normal", scheduled_for=NOW))
    await harness.queue.enqueue(
        JobRun(job_key="future", scheduled_for=NOW + timedelta(hours=1))
    )
    assert (
        run_id(await harness.queue.claim([Lane.HEAVY], "heavy-worker", NOW)) == heavy.id
    )
    claims = await asyncio.gather(
        harness.queue.claim([Lane.DEFAULT], "one", NOW),
        harness.queue.claim([Lane.DEFAULT], "two", NOW),
    )
    assert [run.id for run in claims if run is not None] == [normal.id]
    assert await harness.queue.claim([], "none", NOW) is None


async def test_oldest_due_run_is_claimed_first(harness: QueueHarness) -> None:
    """Claim order follows scheduled time rather than insertion order."""
    later = await harness.queue.enqueue(JobRun(job_key="later", scheduled_for=NOW))
    earlier = await harness.queue.enqueue(
        JobRun(job_key="earlier", scheduled_for=NOW - timedelta(minutes=1))
    )
    assert run_id(await harness.queue.claim([Lane.DEFAULT], "one", NOW)) == earlier.id
    assert run_id(await harness.queue.claim([Lane.DEFAULT], "two", NOW)) == later.id


async def test_heartbeats_reaping_and_stale_completion(harness: QueueHarness) -> None:
    """Only expired running work is abandoned; a stale claimant cannot overwrite it."""
    expired = await harness.queue.enqueue(JobRun(job_key="expired", scheduled_for=NOW))
    healthy = await harness.queue.enqueue(JobRun(job_key="healthy", scheduled_for=NOW))
    queued = await harness.queue.enqueue(JobRun(job_key="queued", scheduled_for=NOW))
    await harness.queue.claim([Lane.DEFAULT], "one", NOW)
    await harness.queue.claim([Lane.DEFAULT], "two", NOW)
    await harness.recorder.heartbeat(healthy.id, "two", NOW + timedelta(minutes=2))
    assert (
        await harness.recorder.reap_abandoned(
            NOW + timedelta(minutes=1), NOW + timedelta(minutes=3)
        )
        == 1
    )
    assert (await harness.reader.get(expired.id)).status is RunStatus.ABANDONED
    assert (await harness.reader.get(healthy.id)).status is RunStatus.RUNNING
    assert (await harness.reader.get(queued.id)).status is RunStatus.QUEUED
    with pytest.raises(LostClaimError):
        await harness.recorder.finish(expired.id, "one", RunStatus.SUCCEEDED, NOW)
    with pytest.raises(LostClaimError):
        await harness.recorder.heartbeat(healthy.id, "wrong", NOW)
    assert run_id(await harness.queue.claim([Lane.DEFAULT], "three", NOW)) == queued.id
    assert await harness.queue.claim([Lane.DEFAULT], "four", NOW) is None
    assert await harness.recorder.reap_abandoned(NOW, NOW) == 0


async def test_idle_worker_liveness_is_independent_of_job_runs(
    harness: QueueHarness,
) -> None:
    """An idle worker still proves it is alive, and old heartbeats expire."""
    assert not await harness.reader.worker_alive(NOW)
    await harness.recorder.worker_heartbeat("idle", NOW)
    await harness.recorder.worker_heartbeat("idle", NOW - timedelta(minutes=1))
    assert await harness.reader.worker_alive(NOW)
    assert not await harness.reader.worker_alive(NOW + timedelta(seconds=1))


async def test_reader_history_active_run_and_scheduled_watermark(
    harness: QueueHarness,
) -> None:
    """Manual requests do not move scheduled cursors; readers filter by job."""
    assert await harness.reader.active_run("x") is None
    assert await harness.reader.last_scheduled_for("x") is None
    scheduled = await harness.queue.enqueue(
        JobRun.for_schedule(JobDefinition(job_key="x"), NOW)
    )
    await harness.queue.enqueue(JobRun(job_key="other", scheduled_for=NOW))
    assert run_id(await harness.reader.active_run("x")) == scheduled.id
    assert await harness.reader.last_scheduled_for("x") == NOW
    await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    await harness.recorder.finish(scheduled.id, "worker", RunStatus.SUCCEEDED, NOW)
    manual = await harness.queue.enqueue(
        JobRun(job_key="x", scheduled_for=NOW + timedelta(days=1))
    )
    assert await harness.reader.last_scheduled_for("x") == NOW
    history = await harness.reader.history("x", limit=1)
    assert [run.id for run in history] == [manual.id]
    with pytest.raises(UnknownRunError):
        await harness.reader.get(uuid7())
    with pytest.raises(UnknownRunError):
        await harness.recorder.heartbeat(uuid7(), "worker", NOW)
    with pytest.raises(UnknownRunError):
        await harness.recorder.finish(uuid7(), "worker", RunStatus.FAILED, NOW)


async def test_concurrent_submissions_deduplicate_the_same_fire(
    harness: QueueHarness,
) -> None:
    """Concurrent tick submissions create only one accepted scheduled occurrence."""
    job = JobDefinition(job_key="x", overlap=Overlap.QUEUE)
    results = await asyncio.gather(
        *(harness.queue.enqueue(JobRun.for_schedule(job, NOW)) for _ in range(3))
    )
    assert len({run.id for run in results}) == 1
    assert len(await harness.reader.history("x", limit=100)) == 1


async def test_concurrent_coalescing_keeps_one_waiting_run(
    harness: QueueHarness,
) -> None:
    """A running job may have only one coalesced waiter, even under concurrent ticks."""
    first = await harness.queue.enqueue(JobRun(job_key="x", scheduled_for=NOW))
    await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    results = await asyncio.gather(
        *(
            harness.queue.enqueue(JobRun(job_key="x", scheduled_for=NOW))
            for _ in range(3)
        )
    )
    assert len({run.id for run in results}) == 1
    assert results[0].id != first.id
    assert len(await harness.reader.history("x", limit=100)) == 2
