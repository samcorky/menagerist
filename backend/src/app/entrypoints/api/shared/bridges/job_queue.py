"""Bridge a module's on-demand job requests to the scheduling queue."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.job_catalogue import get_job_catalogue
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_scheduling_uow,
)
from app.modules.scheduling.application.queue_job_run import (
    QueueJobRun,
    QueueJobRunCommand,
)
from app.platform.database import get_session_factory
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from collections.abc import Callable
    from uuid import UUID

    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.ports.unit_of_work import SchedulingUnitOfWork
    from app.shared_kernel.job_queue import JobQueue


class SchedulingJobQueue:
    """Queue through `QueueJobRun` as the system, in a transaction of its own."""

    def __init__(
        self, uow: Callable[[], SchedulingUnitOfWork], registry: JobRegistry
    ) -> None:
        self._uow = uow
        self._registry = registry

    async def request(self, job_key: str, *, requested_by: UUID) -> None:
        """Queue the job, or leave the run already waiting to start in place."""
        await QueueJobRun(self._uow(), get_access_guard(), self._registry).handle(
            QueueJobRunCommand(
                job_key=job_key, requested_by=requested_by, now=datetime.now(UTC)
            ),
            SYSTEM_ACTOR,
        )


def get_job_queue() -> JobQueue:
    """The queue for this process, over the database and the job catalogue."""
    factory = get_session_factory()
    return SchedulingJobQueue(
        lambda: create_scheduling_uow(factory), get_job_catalogue().registry
    )
