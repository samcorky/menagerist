"""Wire the scheduling API to its use cases."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.job_catalogue import (
    get_job_catalogue,
    get_schedule_source,
)
from app.modules.scheduling.adapters.persistence.job_run_reader import (
    SqlAlchemyJobRunReader,
)
from app.modules.scheduling.adapters.persistence.unit_of_work import (
    create_scheduling_uow,
)
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.application.get_job_history import GetJobHistory
from app.modules.scheduling.application.list_jobs import ListJobs
from app.modules.scheduling.application.preview_schedule import PreviewSchedule
from app.modules.scheduling.application.run_job_now import RunJobNow
from app.modules.scheduling.domain.registry import JobRegistry
from app.modules.scheduling.ports.job_run_reader import JobRunReader
from app.modules.scheduling.ports.schedule_source import ScheduleSource
from app.platform.database import get_session_factory

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.shared_kernel.access_guard import AccessGuard


def get_preview_schedule_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> PreviewSchedule:
    return PreviewSchedule(CronScheduleEvaluator(), guard)


async def get_job_run_reader(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
) -> AsyncIterator[JobRunReader]:
    """Read job runs through a short-lived session, for queries."""
    async with factory() as session:
        yield SqlAlchemyJobRunReader(session)


def get_job_registry() -> JobRegistry:
    return get_job_catalogue().registry


def get_list_jobs_use_case(
    reader: Annotated[JobRunReader, Depends(get_job_run_reader)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    registry: Annotated[JobRegistry, Depends(get_job_registry)],
    schedules: Annotated[ScheduleSource, Depends(get_schedule_source)],
) -> ListJobs:
    return ListJobs(reader, guard, registry, schedules, CronScheduleEvaluator())


def get_job_history_use_case(
    reader: Annotated[JobRunReader, Depends(get_job_run_reader)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    registry: Annotated[JobRegistry, Depends(get_job_registry)],
) -> GetJobHistory:
    return GetJobHistory(reader, guard, registry)


def get_run_job_now_use_case(
    factory: Annotated[async_sessionmaker[AsyncSession], Depends(get_session_factory)],
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
    registry: Annotated[JobRegistry, Depends(get_job_registry)],
) -> RunJobNow:
    return RunJobNow(create_scheduling_uow(factory), guard, registry)
