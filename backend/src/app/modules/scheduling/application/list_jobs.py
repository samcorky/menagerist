"""Read-only job metadata, active work and next-fire previews."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.job_run import JobRun, utc_instant
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.jobs import JobDefinition
from app.shared_kernel.paging import (
    Page,
    SearchedPagedQuery,
    page_rows,
    timestamp_value,
)
from app.shared_kernel.text import matches_text

if TYPE_CHECKING:
    from app.modules.scheduling.domain.registry import JobRegistry
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.modules.scheduling.ports.schedule_source import ScheduleSource
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class JobSort(StrEnum):
    """What the jobs can be sorted by: fields of the response."""

    TITLE = "title"
    NEXT_RUN_AT = "next_run_at"
    LAST_RUN = "last_run"


@dataclass(kw_only=True)
class ListJobsQuery(SearchedPagedQuery[JobSort]):
    """Request for a page of jobs, by title unless `sort` says otherwise.

    `now` and `timezone` are the instant and instance timezone used for next-run
    previews. `q` keeps the jobs whose title or description contains it.
    """

    now: datetime
    timezone: str


@dataclass(frozen=True, kw_only=True)
class JobStatus:
    """A job definition with its effective schedule and execution state."""

    definition: JobDefinition
    expression: str | None
    next_run_at: datetime | None
    active_run: JobRun | None
    last_run: JobRun | None = None


def _job_id(status: JobStatus) -> uuid.UUID:
    """A job has a key, not an id: a stable one for the cursor to tie-break on."""
    return uuid.uuid5(uuid.NAMESPACE_URL, status.definition.job_key)


def _last_run_at(status: JobStatus) -> str | None:
    run = status.last_run
    if run is None:
        return None
    return timestamp_value(run.started_at or run.scheduled_for)


class ListJobs(QueryHandler[JobRunReader, ListJobsQuery, Page[JobStatus]]):
    """List registered jobs without initialising or advancing schedule cursors.

    The registry is small and fixed, so every job is read and then ordered, searched
    and paged in memory (`page_rows`), the same way a person's own few rows are.
    """

    access: ClassVar[Access] = Requires(SchedulingPermission.READ)

    def __init__(
        self,
        repos: JobRunReader,
        guard: AccessGuard,
        registry: JobRegistry,
        schedules: ScheduleSource,
        evaluator: ScheduleEvaluator,
    ) -> None:
        super().__init__(repos, guard)
        self._registry = registry
        self._schedules = schedules
        self._evaluator = evaluator

    async def _handle(self, request: ListJobsQuery, actor: Actor) -> Page[JobStatus]:
        now = utc_instant(request.now)
        statuses: list[JobStatus] = []
        for job in self._registry.all():
            if not matches_text(request.q, job.title, job.description):
                continue
            expression = (
                (await self._schedules.schedule_for(job.schedule_key) or None)
                if job.schedule_key is not None
                else None
            )
            next_run = (
                await self._evaluator.next_fire(expression, request.timezone, after=now)
                if expression
                else None
            )
            recent = await self._repos.history(job.job_key, limit=1)
            statuses.append(
                JobStatus(
                    definition=job,
                    expression=expression,
                    next_run_at=next_run,
                    active_run=await self._repos.active_run(job.job_key),
                    last_run=recent[0] if recent else None,
                )
            )
        return page_rows(
            statuses,
            request.page_request(JobSort.TITLE),
            id_of=_job_id,
            values={
                JobSort.TITLE: lambda s: s.definition.title.casefold(),
                JobSort.NEXT_RUN_AT: lambda s: (
                    None if s.next_run_at is None else timestamp_value(s.next_run_at)
                ),
                JobSort.LAST_RUN: _last_run_at,
            },
        )
