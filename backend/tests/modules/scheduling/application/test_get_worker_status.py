"""Read worker liveness through the guarded query boundary."""

from datetime import UTC, datetime, timedelta

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.in_memory_job_run_reader import (
    InMemoryJobRunReader,
)
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.application.get_worker_status import (
    GetWorkerStatus,
    GetWorkerStatusQuery,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR
from app.shared_kernel.errors import ForbiddenError


async def test_liveness_query_uses_cutoff_and_system_access() -> None:
    """The query includes the cutoff and refuses anonymous inspection."""
    now = datetime(2026, 10, 27, tzinfo=UTC)
    store = InMemorySchedulingStore(workers={"worker": now})
    query = GetWorkerStatus(InMemoryJobRunReader(store), get_access_guard())
    assert await query.handle(GetWorkerStatusQuery(since=now), SYSTEM_ACTOR)
    assert not await query.handle(
        GetWorkerStatusQuery(since=now + timedelta(seconds=1)), SYSTEM_ACTOR
    )
    with pytest.raises(ForbiddenError):
        await query.handle(GetWorkerStatusQuery(since=now), ANONYMOUS_ACTOR)


async def test_liveness_query_targets_an_individual_worker() -> None:
    """Container health must inspect its own process rather than any worker."""
    now = datetime(2026, 10, 27, tzinfo=UTC)
    store = InMemorySchedulingStore(workers={"healthy": now})
    query = GetWorkerStatus(InMemoryJobRunReader(store), get_access_guard())
    assert await query.handle(
        GetWorkerStatusQuery(since=now, worker_id="healthy"), SYSTEM_ACTOR
    )
    assert not await query.handle(
        GetWorkerStatusQuery(since=now, worker_id="missing"), SYSTEM_ACTOR
    )
