"""Compose first-class in-memory adapters using the shared unit of work."""

from typing import TYPE_CHECKING

from app.modules.scheduling.adapters.persistence.in_memory_job_run_queue import (
    InMemoryJobRunQueue,
)
from app.modules.scheduling.adapters.persistence.in_memory_job_run_reader import (
    InMemoryJobRunReader,
)
from app.modules.scheduling.adapters.persistence.in_memory_job_run_recorder import (
    InMemoryJobRunRecorder,
)
from app.modules.scheduling.adapters.persistence.in_memory_schedule_cursor_store import (  # noqa: E501
    InMemoryScheduleCursorStore,
)
from app.modules.scheduling.ports.unit_of_work import SchedulingRepos
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )


def build_in_memory_scheduling_repos(store: InMemorySchedulingStore) -> SchedulingRepos:
    """Bind the module's in-memory ports to a shared store."""
    return SchedulingRepos(
        queue=InMemoryJobRunQueue(store),
        reader=InMemoryJobRunReader(store),
        recorder=InMemoryJobRunRecorder(store),
        cursors=InMemoryScheduleCursorStore(store),
    )


def create_in_memory_scheduling_uow(
    store: InMemorySchedulingStore,
) -> InMemoryUnitOfWork[SchedulingRepos]:
    """Use the standard in-memory transaction signal implementation."""
    return InMemoryUnitOfWork(build_in_memory_scheduling_repos(store))
