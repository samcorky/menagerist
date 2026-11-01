"""Administrative history queries for registered jobs."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.job_run import JobRun
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True, kw_only=True)
class GetJobHistoryQuery:
    """The registered job and maximum number of recent runs to return."""

    job_key: str
    limit: int = 100

    def __post_init__(self) -> None:
        """Reject invalid result limits before querying history."""
        if self.limit < 1:
            raise ValidationError("History limit must be positive")


class GetJobHistory(QueryHandler[JobRunReader, GetJobHistoryQuery, list[JobRun]]):
    """Return recent history without a write transaction."""

    access: ClassVar[Access] = Requires(SchedulingPermission.READ)

    def __init__(
        self, repos: JobRunReader, guard: AccessGuard, registry: JobRegistry
    ) -> None:
        super().__init__(repos, guard)
        self._registry = registry

    async def _handle(self, request: GetJobHistoryQuery, actor: Actor) -> list[JobRun]:
        self._registry.get(request.job_key)
        return await self._repos.history(request.job_key, limit=request.limit)
