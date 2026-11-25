"""Queueing a job for work someone started in another module."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.application.queue_job_run import (
    QueueJobRun,
    QueueJobRunCommand,
)
from app.modules.scheduling.domain.errors import (
    OnDemandNotAllowedError,
    UnknownJobError,
)
from app.modules.scheduling.domain.job_run import RunStatus
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap

NOW = datetime(2026, 11, 23, 19, tzinfo=UTC)
PERSON = uuid7()
IMPORTS = JobDefinition(job_key="transfer.item_imports", lane=Lane.HEAVY)


def _queue(store: InMemorySchedulingStore, *jobs: JobDefinition) -> QueueJobRun:
    return QueueJobRun(
        create_in_memory_scheduling_uow(store),
        get_access_guard(),
        JobRegistry(jobs or [IMPORTS]),
    )


def _command(job_key: str = "transfer.item_imports") -> QueueJobRunCommand:
    return QueueJobRunCommand(job_key=job_key, requested_by=PERSON, now=NOW)


async def test_queues_a_run_with_the_requester_and_the_job_policy() -> None:
    """The run carries who asked and the job's lane and overlap."""
    store = InMemorySchedulingStore()
    run = await _queue(store).handle(_command(), SYSTEM_ACTOR)
    assert run.requested_by == PERSON
    assert run.lane is Lane.HEAVY
    assert run.overlap is Overlap.COALESCE
    assert run.scheduled_for == NOW
    assert [r.id for r in store.runs.values()] == [run.id]


async def test_a_second_request_reuses_the_waiting_run() -> None:
    """A burst of requests queues one run, which drains the work they share."""
    store = InMemorySchedulingStore()
    first = await _queue(store).handle(_command(), SYSTEM_ACTOR)
    second = await _queue(store).handle(_command(), SYSTEM_ACTOR)
    assert second.id == first.id
    assert len(store.runs) == 1


async def test_a_request_while_a_run_drains_queues_one_more_behind_it() -> None:
    """A running drain may already have looked for work, so it is never reused."""
    store = InMemorySchedulingStore()
    running = await _queue(store).handle(_command(), SYSTEM_ACTOR)
    store.runs[running.id].status = RunStatus.RUNNING
    behind = await _queue(store).handle(_command(), SYSTEM_ACTOR)
    again = await _queue(store).handle(_command(), SYSTEM_ACTOR)
    assert behind.id != running.id
    assert behind.status is RunStatus.QUEUED
    assert again.id == behind.id
    assert len(store.runs) == 2


@pytest.mark.parametrize("overlap", [Overlap.SKIP, Overlap.QUEUE])
async def test_refuses_a_job_that_does_not_coalesce(overlap: Overlap) -> None:
    """Skipping would strand work; queueing would stack runs with nothing to do."""
    store = InMemorySchedulingStore()
    queue = _queue(store, JobDefinition(job_key="stacked", overlap=overlap))
    with pytest.raises(OnDemandNotAllowedError):
        await queue.handle(_command("stacked"), SYSTEM_ACTOR)
    assert not store.runs


async def test_refuses_an_unknown_job() -> None:
    """The key must be registered."""
    store = InMemorySchedulingStore()
    with pytest.raises(UnknownJobError):
        await _queue(store).handle(_command("missing"), SYSTEM_ACTOR)
    assert not store.runs


async def test_only_the_system_may_queue() -> None:
    """People reach it only through the module that owns the work."""
    store = InMemorySchedulingStore()
    admin = Actor(id=uuid7(), roles=frozenset({"admin"}))
    with pytest.raises(ForbiddenError):
        await _queue(store).handle(_command(), admin)
    assert not store.runs
