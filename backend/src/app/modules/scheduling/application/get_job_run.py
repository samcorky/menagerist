"""Read one execution after synchronous CLI submission."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar
from uuid import UUID

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.job_run import JobRun
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetJobRunQuery:
    """The identifier of a requested execution."""

    run_id: UUID


class GetJobRun(QueryHandler[JobRunReader, GetJobRunQuery, JobRun]):
    """Read persisted execution state without opening a writing unit of work."""

    access: ClassVar[Access] = Requires(SchedulingPermission.READ)

    async def _handle(self, request: GetJobRunQuery, actor: Actor) -> JobRun:
        return await self._repos.get(request.run_id)
