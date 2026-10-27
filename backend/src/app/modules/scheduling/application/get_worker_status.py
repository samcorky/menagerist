"""Inspect worker liveness without opening a writing transaction."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetWorkerStatusQuery:
    """The earliest heartbeat that counts as a live worker."""

    since: datetime
    worker_id: str | None = None


class GetWorkerStatus(QueryHandler[JobRunReader, GetWorkerStatusQuery, bool]):
    """Report whether the requested worker scope has checked in since the cutoff."""

    access: ClassVar[Access] = System()

    async def _handle(self, request: GetWorkerStatusQuery, actor: Actor) -> bool:
        return await self._repos.worker_alive(
            request.since, worker_id=request.worker_id
        )
