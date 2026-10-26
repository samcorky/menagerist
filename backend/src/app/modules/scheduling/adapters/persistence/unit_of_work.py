"""Compose SQLAlchemy and in-memory adapters using shared units of work."""

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
from app.modules.scheduling.adapters.persistence.job_run_queue import (
    SqlAlchemyJobRunQueue,
)
from app.modules.scheduling.adapters.persistence.job_run_reader import (
    SqlAlchemyJobRunReader,
)
from app.modules.scheduling.adapters.persistence.job_run_recorder import (
    SqlAlchemyJobRunRecorder,
)
from app.modules.scheduling.adapters.persistence.schedule_cursor_store import (
    SqlAlchemyScheduleCursorStore,
)
from app.modules.scheduling.ports.unit_of_work import SchedulingRepos
from app.platform.unit_of_work import SqlAlchemySessionUnitOfWork
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )
    from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork


def build_scheduling_repos(session: AsyncSession) -> SchedulingRepos:
    """Bind all durable scheduling ports to the caller's existing transaction."""
    return SchedulingRepos(
        queue=SqlAlchemyJobRunQueue(session),
        reader=SqlAlchemyJobRunReader(session),
        recorder=SqlAlchemyJobRunRecorder(session),
        cursors=SqlAlchemyScheduleCursorStore(session),
    )


def create_scheduling_uow(
    session_factory: async_sessionmaker[AsyncSession],
) -> SchedulingUnitOfWork:
    """Use the common SQLAlchemy unit of work for standalone scheduler commands."""
    return SqlAlchemySessionUnitOfWork(session_factory, build_scheduling_repos)


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
