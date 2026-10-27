"""History retention is a guarded application transaction."""

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


async def test_pruning_commits_and_refuses_non_system_callers() -> None:
    """Only the system actor can remove operational history."""
    uow = create_in_memory_scheduling_uow(InMemorySchedulingStore())
    use_case = PruneJobRuns(uow, get_access_guard())
    request = PruneJobRunsCommand(keep_per_job=100)
    with pytest.raises(ForbiddenError):
        await use_case.handle(request, ANONYMOUS_ACTOR)
    assert not uow.committed
    assert await use_case.handle(request, SYSTEM_ACTOR) == 0
    assert uow.committed


@pytest.mark.parametrize("keep", [0, -1])
def test_retention_must_be_positive(keep: int) -> None:
    """A caller cannot accidentally erase all completed history."""
    with pytest.raises(ValidationError):
        PruneJobRunsCommand(keep_per_job=keep)
