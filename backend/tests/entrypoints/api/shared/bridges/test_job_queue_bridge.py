"""The job queue bridge queues on-demand runs through the scheduling module."""

from uuid import uuid7

import pytest

from app.entrypoints.api.shared.bridges.job_queue import SchedulingJobQueue
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.domain.errors import OnDemandNotAllowedError
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.jobs import JobDefinition, Overlap


def _queue(store: InMemorySchedulingStore) -> SchedulingJobQueue:
    registry = JobRegistry(
        [
            JobDefinition(job_key="imports"),
            JobDefinition(job_key="stacked", overlap=Overlap.QUEUE),
        ]
    )
    return SchedulingJobQueue(lambda: create_in_memory_scheduling_uow(store), registry)


async def test_requests_share_one_waiting_run_for_whoever_asked_first() -> None:
    """Each request opens its own transaction, and a waiting run is reused."""
    store = InMemorySchedulingStore()
    first, second = uuid7(), uuid7()
    await _queue(store).request("imports", requested_by=first)
    await _queue(store).request("imports", requested_by=second)
    [run] = store.runs.values()
    assert run.job_key == "imports"
    assert run.requested_by == first


async def test_passes_on_a_refusal() -> None:
    """A job that does not coalesce cannot be queued this way."""
    store = InMemorySchedulingStore()
    with pytest.raises(OnDemandNotAllowedError):
        await _queue(store).request("stacked", requested_by=uuid7())
    assert not store.runs
