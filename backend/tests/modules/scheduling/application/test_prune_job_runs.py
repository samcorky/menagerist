"""History retention is a guarded application transaction."""

from datetime import UTC, datetime, timedelta

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.persistence.in_memory_store import (
    InMemorySchedulingStore,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_in_memory_scheduling_uow,
)
from app.modules.scheduling.application.prune_job_runs import (
    PruneJobRuns,
    PruneJobRunsCommand,
)
from app.shared_kernel.actor import ANONYMOUS_ACTOR, SYSTEM_ACTOR
from app.shared_kernel.errors import ForbiddenError, ValidationError

BEFORE = datetime(2026, 10, 24, tzinfo=UTC)


async def test_pruning_commits_and_refuses_non_system_callers() -> None:
    """Only the system actor can remove operational history."""
    uow = create_in_memory_scheduling_uow(InMemorySchedulingStore())
    use_case = PruneJobRuns(uow, get_access_guard())
    request = PruneJobRunsCommand(keep_per_job=100, worker_heartbeats_before=BEFORE)
    with pytest.raises(ForbiddenError):
        await use_case.handle(request, ANONYMOUS_ACTOR)
    assert not uow.committed
    assert await use_case.handle(request, SYSTEM_ACTOR) == 0
    assert uow.committed


@pytest.mark.parametrize("keep", [0, -1])
def test_retention_must_be_positive(keep: int) -> None:
    """A caller cannot accidentally erase all completed history."""
    with pytest.raises(ValidationError):
        PruneJobRunsCommand(keep_per_job=keep, worker_heartbeats_before=BEFORE)


async def test_pruning_also_forgets_workers_silent_since_the_cutoff() -> None:
    """Stopped workers leave a heartbeat row each; the same job tidies them."""
    store = InMemorySchedulingStore()
    store.workers["old"] = BEFORE - timedelta(seconds=1)
    store.workers["new"] = BEFORE
    use_case = PruneJobRuns(create_in_memory_scheduling_uow(store), get_access_guard())
    request = PruneJobRunsCommand(keep_per_job=100, worker_heartbeats_before=BEFORE)
    await use_case.handle(request, SYSTEM_ACTOR)
    assert set(store.workers) == {"new"}
