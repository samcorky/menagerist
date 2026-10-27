"""Queue contracts shared by the in-memory and Postgres adapters."""

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
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    build_scheduling_repos,
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


@pytest.mark.parametrize("keep", [1, 2, 10])
@pytest.mark.parametrize("tied_timestamps", [True, False])
async def test_pruning_keeps_completed_history_per_job_and_all_active_work(
    harness: QueueHarness,
    keep: int,
    tied_timestamps: bool,
) -> None:
    """Terminal outcomes share a quota; queued and running work never consume it."""
    retained = {}
    for job_key in ("first", "second"):
        for index, status in enumerate(
            (
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.SKIPPED,
                RunStatus.ABANDONED,
            )
        ):
            run = JobRun(
                id=UUID(int=index + 1 + (100 if job_key == "second" else 0)),
                job_key=job_key,
                created_at=NOW if tied_timestamps else NOW - timedelta(seconds=index),
                scheduled_for=NOW,
            )
            await harness.queue.enqueue(run)
            await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
            if status is RunStatus.ABANDONED:
                await harness.recorder.reap_abandoned(NOW + timedelta(seconds=1), NOW)
            else:
                await harness.recorder.finish(run.id, "worker", status, NOW)
    for job_key in ("first", "second"):
        running = await harness.queue.enqueue(
            JobRun.create(job_key=job_key, scheduled_for=NOW)
        )
        await harness.queue.claim([Lane.DEFAULT], "worker", NOW, run_id=running.id)
        queued = await harness.queue.enqueue(
            JobRun.create(job_key=job_key, scheduled_for=NOW)
        )
        retained[job_key] = {running.id, queued.id}
        ordered = [4, 3, 2, 1] if tied_timestamps else [1, 2, 3, 4]
        retained[job_key].update(
            UUID(int=value + (100 if job_key == "second" else 0))
            for value in ordered[:keep]
        )

    removed = await harness.recorder.prune_history(keep_per_job=keep)
    assert removed == 2 * max(4 - keep, 0)
    assert await harness.recorder.prune_history(keep_per_job=keep) == 0
    for job_key, ids in retained.items():
        history = await harness.reader.history(job_key, limit=100)
        assert {run.id for run in history} == ids


@dataclass(kw_only=True)
class QueueHarness:
    """The contract exposes ports so another adapter can use the same tests."""

    queue: JobRunQueue
    reader: JobRunReader
    recorder: JobRunRecorder


@pytest.fixture
def memory_harness() -> QueueHarness:
    """Wire all three adapters to the same in-memory store."""
    store = InMemorySchedulingStore()
    return QueueHarness(
        queue=InMemoryJobRunQueue(store),
        reader=InMemoryJobRunReader(store),
        recorder=InMemoryJobRunRecorder(store),
    )


@pytest.fixture(
    params=["memory", pytest.param("postgres", marks=pytest.mark.integration)]
)
def harness(
    request: pytest.FixtureRequest, memory_harness: QueueHarness
) -> QueueHarness:
    """Exercise the same contract against both session-scoped implementations."""
    if request.param == "memory":
        return memory_harness
    repos = build_scheduling_repos(request.getfixturevalue("db_session"))
    return QueueHarness(queue=repos.queue, reader=repos.reader, recorder=repos.recorder)


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
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=policy)
    )
    await harness.queue.claim([Lane.DEFAULT], "first", NOW)
    second = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=policy)
    )
    third = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=policy)
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
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE),
        deduplicate_active=True,
    )
    repeated = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE),
        deduplicate_active=True,
    )
    assert repeated.id == first.id


async def test_lanes_due_times_and_two_workers(harness: QueueHarness) -> None:
    """A busy heavy job cannot block a due default job or be claimed twice."""
    heavy = await harness.queue.enqueue(
        JobRun.create(job_key="heavy", scheduled_for=NOW, lane=Lane.HEAVY)
    )
    normal = await harness.queue.enqueue(
        JobRun.create(job_key="normal", scheduled_for=NOW)
    )
    await harness.queue.enqueue(
        JobRun.create(job_key="future", scheduled_for=NOW + timedelta(hours=1))
    )
    assert (
        run_id(await harness.queue.claim([Lane.HEAVY], "heavy-worker", NOW)) == heavy.id
    )
    claims = [
        await harness.queue.claim([Lane.DEFAULT], "one", NOW),
        await harness.queue.claim([Lane.DEFAULT], "two", NOW),
    ]
    assert [run.id for run in claims if run is not None] == [normal.id]
    assert await harness.queue.claim([], "none", NOW) is None


async def test_oldest_due_run_is_claimed_first(harness: QueueHarness) -> None:
    """Claim order follows scheduled time rather than insertion order."""
    later = await harness.queue.enqueue(
        JobRun.create(job_key="later", scheduled_for=NOW)
    )
    earlier = await harness.queue.enqueue(
        JobRun.create(job_key="earlier", scheduled_for=NOW - timedelta(minutes=1))
    )
    assert run_id(await harness.queue.claim([Lane.DEFAULT], "one", NOW)) == earlier.id
    assert run_id(await harness.queue.claim([Lane.DEFAULT], "two", NOW)) == later.id


async def test_heartbeats_reaping_and_stale_completion(harness: QueueHarness) -> None:
    """Only expired running work is abandoned; a stale claimant cannot overwrite it."""
    expired = await harness.queue.enqueue(
        JobRun.create(job_key="expired", scheduled_for=NOW)
    )
    healthy = await harness.queue.enqueue(
        JobRun.create(job_key="healthy", scheduled_for=NOW)
    )
    queued = await harness.queue.enqueue(
        JobRun.create(job_key="queued", scheduled_for=NOW)
    )
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


async def test_worker_probe_cannot_be_masked_by_another_live_worker(
    harness: QueueHarness,
) -> None:
    """An individual probe distinguishes stale, missing and healthy workers."""
    await harness.recorder.worker_heartbeat("stale", NOW - timedelta(minutes=10))
    await harness.recorder.worker_heartbeat("healthy", NOW)
    assert await harness.reader.worker_alive(NOW)
    assert await harness.reader.worker_alive(NOW, worker_id="healthy")
    assert not await harness.reader.worker_alive(NOW, worker_id="stale")
    assert not await harness.reader.worker_alive(NOW, worker_id="missing")


async def test_reader_history_active_run_and_scheduled_watermark(
    harness: QueueHarness,
) -> None:
    """Manual requests do not move scheduled cursors; readers filter by job."""
    assert await harness.reader.active_run("x") is None
    assert await harness.reader.last_scheduled_for("x") is None
    scheduled = await harness.queue.enqueue(
        JobRun.for_schedule(JobDefinition(job_key="x"), NOW)
    )
    await harness.queue.enqueue(JobRun.create(job_key="other", scheduled_for=NOW))
    assert run_id(await harness.reader.active_run("x")) == scheduled.id
    assert await harness.reader.last_scheduled_for("x") == NOW
    await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    await harness.recorder.finish(scheduled.id, "worker", RunStatus.SUCCEEDED, NOW)
    manual = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW + timedelta(days=1))
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
    memory_harness: QueueHarness,
) -> None:
    """Concurrent tick submissions create only one accepted scheduled occurrence."""
    harness = memory_harness
    job = JobDefinition(job_key="x", overlap=Overlap.QUEUE)
    results = await asyncio.gather(
        *(harness.queue.enqueue(JobRun.for_schedule(job, NOW)) for _ in range(3))
    )
    assert len({run.id for run in results}) == 1
    assert len(await harness.reader.history("x", limit=100)) == 1


async def test_concurrent_coalescing_keeps_one_waiting_run(
    memory_harness: QueueHarness,
) -> None:
    """A running job may have only one coalesced waiter, even under concurrent ticks."""
    harness = memory_harness
    first = await harness.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
    await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    results = await asyncio.gather(
        *(
            harness.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
            for _ in range(3)
        )
    )
    assert len({run.id for run in results}) == 1
    assert results[0].id != first.id
    assert len(await harness.reader.history("x", limit=100)) == 2


async def test_enqueued_input_and_returned_runs_are_detached(
    harness: QueueHarness,
) -> None:
    """Mutating either side of enqueue cannot rewrite persisted queue state."""
    submitted = JobRun.create(job_key="x", scheduled_for=NOW)
    accepted = await harness.queue.enqueue(submitted)
    submitted.scheduled_for = NOW + timedelta(days=1)
    accepted.status = RunStatus.FAILED
    stored = await harness.reader.get(accepted.id)
    assert stored.scheduled_for == NOW
    assert stored.status is RunStatus.QUEUED
    assert (
        run_id(await harness.queue.claim([Lane.DEFAULT], "worker", NOW)) == accepted.id
    )


async def test_every_reader_returns_detached_runs(harness: QueueHarness) -> None:
    """Get, active-run and history results cannot mutate the stored entity."""
    accepted = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW)
    )
    by_id = await harness.reader.get(accepted.id)
    active = await harness.reader.active_run("x")
    assert active is not None
    history = await harness.reader.history("x", limit=1)
    by_id.status = RunStatus.FAILED
    active.worker_id = "wrong"
    history[0].job_key = "changed"
    stored = await harness.reader.get(accepted.id)
    assert stored.status is RunStatus.QUEUED
    assert stored.worker_id is None
    assert stored.job_key == "x"


async def test_claim_results_and_old_reads_do_not_alias_stored_transitions(
    harness: QueueHarness,
) -> None:
    """Detached results preserve ownership checks and historical snapshots."""
    accepted = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW)
    )
    claimed = await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    assert claimed is not None
    old = await harness.reader.get(accepted.id)
    claimed.worker_id = "intruder"
    await harness.recorder.heartbeat(accepted.id, "worker", NOW + timedelta(seconds=1))
    await harness.recorder.finish(
        accepted.id, "worker", RunStatus.SUCCEEDED, NOW + timedelta(seconds=2)
    )
    assert old.status is RunStatus.RUNNING
    assert old.heartbeat_at == NOW
    stored = await harness.reader.get(accepted.id)
    assert stored.worker_id == "worker"
    assert stored.status is RunStatus.SUCCEEDED


async def test_deduplicated_enqueue_returns_a_detached_run(
    harness: QueueHarness,
) -> None:
    """Reusing an accepted or coalesced run must not expose the stored instance."""
    first = await harness.queue.enqueue(JobRun.create(job_key="x", scheduled_for=NOW))
    same_id = await harness.queue.enqueue(first)
    same_id.error = "changed"
    coalesced = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW)
    )
    coalesced.status = RunStatus.SUCCEEDED
    stored = await harness.reader.get(first.id)
    assert stored.error is None
    assert stored.status is RunStatus.QUEUED


async def test_active_work_prefers_creation_order_then_running(
    harness: QueueHarness,
) -> None:
    """The oldest queued request is active even when another is due sooner."""
    first = JobRun.create(
        job_key="x", scheduled_for=NOW + timedelta(days=1), overlap=Overlap.QUEUE
    )
    first.created_at = NOW - timedelta(minutes=1)
    await harness.queue.enqueue(first)
    next_run = JobRun.create(job_key="x", scheduled_for=NOW, overlap=Overlap.QUEUE)
    next_run.created_at = NOW
    second = await harness.queue.enqueue(next_run)
    assert run_id(await harness.reader.active_run("x")) == first.id
    assert (
        run_id(
            await harness.queue.enqueue(
                JobRun.create(job_key="x", scheduled_for=NOW), deduplicate_active=True
            )
        )
        == first.id
    )
    assert run_id(await harness.queue.claim([Lane.DEFAULT], "worker", NOW)) == second.id
    assert run_id(await harness.reader.active_run("x")) == second.id


@pytest.mark.parametrize(
    "outcome", [RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.SKIPPED]
)
async def test_terminal_outcomes_and_requester_round_trip(
    harness: QueueHarness, outcome: RunStatus
) -> None:
    """Execution outcomes, audit identity and errors survive a storage round trip."""
    requester = uuid7()
    accepted = await harness.queue.enqueue(
        JobRun.create(job_key="x", scheduled_for=NOW, requested_by=requester)
    )
    await harness.queue.claim([Lane.DEFAULT], "worker", NOW)
    await harness.recorder.heartbeat(accepted.id, "worker", NOW - timedelta(minutes=1))
    await harness.recorder.finish(
        accepted.id, "worker", outcome, NOW + timedelta(seconds=1), error="reason"
    )
    stored = await harness.reader.get(accepted.id)
    assert stored.requested_by == requester
    assert stored.status is outcome
    assert stored.started_at == stored.heartbeat_at == NOW
    assert stored.finished_at == NOW + timedelta(seconds=1)
    assert stored.error == "reason"


async def test_targeted_claim_cannot_take_another_run_or_overlap(
    harness: QueueHarness,
) -> None:
    """Synchronous CLI execution claims only its requested queued occurrence."""
    first = await harness.queue.enqueue(
        JobRun.create(job_key="first", scheduled_for=NOW)
    )
    target = await harness.queue.enqueue(
        JobRun.create(job_key="target", scheduled_for=NOW, overlap=Overlap.QUEUE)
    )
    waiting = await harness.queue.enqueue(
        JobRun.create(job_key="target", scheduled_for=NOW, overlap=Overlap.QUEUE)
    )
    assert (
        run_id(await harness.queue.claim([Lane.DEFAULT], "cli", NOW, run_id=target.id))
        == target.id
    )
    assert (
        await harness.queue.claim([Lane.DEFAULT], "other", NOW, run_id=waiting.id)
        is None
    )
    assert (
        await harness.queue.claim([Lane.DEFAULT], "other", NOW, run_id=uuid7()) is None
    )
    assert (await harness.reader.get(first.id)).status is RunStatus.QUEUED
