"""Administrative history queries for registered jobs."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.job_run import JobRun
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.paging import (
    MAX_PAGE_ROWS,
    Page,
    PagedQuery,
    SortOrder,
    page_rows,
    timestamp_value,
)

if TYPE_CHECKING:
    from datetime import datetime

    from app.modules.scheduling.domain.registry import JobRegistry
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class JobRunSort(StrEnum):
    """What a job's runs can be sorted by: fields of the response."""

    CREATED_AT = "created_at"
    SCHEDULED_FOR = "scheduled_for"
    STATUS = "status"
    STARTED_AT = "started_at"
    FINISHED_AT = "finished_at"


@dataclass(kw_only=True)
class GetJobHistoryQuery(PagedQuery[JobRunSort]):
    """The registered job whose recent runs to page through, newest first."""

    job_key: str
    order: SortOrder = SortOrder.DESC

    def __post_init__(self) -> None:
        """Reject invalid result limits before querying history."""
        if self.limit < 1:
            raise ValidationError("History limit must be positive")


class GetJobHistory(QueryHandler[JobRunReader, GetJobHistoryQuery, Page[JobRun]]):
    """Return recent history without a write transaction."""

    access: ClassVar[Access] = Requires(SchedulingPermission.READ)

    def __init__(
        self, repos: JobRunReader, guard: AccessGuard, registry: JobRegistry
    ) -> None:
        super().__init__(repos, guard)
        self._registry = registry

    async def _handle(self, request: GetJobHistoryQuery, actor: Actor) -> Page[JobRun]:
        self._registry.get(request.job_key)
        runs = await self._repos.history(request.job_key, limit=MAX_PAGE_ROWS)
        return page_rows(
            runs,
            request.page_request(JobRunSort.CREATED_AT),
            id_of=lambda run: run.id,
            values={
                JobRunSort.CREATED_AT: lambda run: timestamp_value(run.created_at),
                JobRunSort.SCHEDULED_FOR: lambda run: timestamp_value(
                    run.scheduled_for
                ),
                JobRunSort.STATUS: lambda run: str(run.status),
                JobRunSort.STARTED_AT: lambda run: _optional_time(run.started_at),
                JobRunSort.FINISHED_AT: lambda run: _optional_time(run.finished_at),
            },
        )


def _optional_time(moment: datetime | None) -> str | None:
    return None if moment is None else timestamp_value(moment)
