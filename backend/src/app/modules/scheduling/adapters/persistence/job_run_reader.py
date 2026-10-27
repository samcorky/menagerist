"""Session-bound read-side queries for durable executions."""

from typing import TYPE_CHECKING

from sqlalchemy import case, exists, func, select

from app.modules.scheduling.adapters.persistence.job_run_mapping import to_domain
from app.modules.scheduling.adapters.persistence.models import (
    JobRunModel,
    WorkerHeartbeatModel,
)
from app.modules.scheduling.domain.errors import UnknownRunError
from app.modules.scheduling.domain.job_run import RunStatus

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.scheduling.domain.job_run import JobRun


class SqlAlchemyJobRunReader:
    """Return detached snapshots without committing the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, run_id: UUID) -> JobRun:
        """Return a run or raise the shared missing-run error."""
        model = await self._session.get(JobRunModel, run_id, populate_existing=True)
        if model is None:
            raise UnknownRunError(str(run_id))
        return to_domain(model)

    async def active_run(self, job_key: str) -> JobRun | None:
        """Prefer running work, otherwise the oldest queued occurrence."""
        model = await self._session.scalar(
            select(JobRunModel)
            .where(
                JobRunModel.job_key == job_key,
                JobRunModel.status.in_([RunStatus.RUNNING, RunStatus.QUEUED]),
            )
            .order_by(
                case((JobRunModel.status == RunStatus.RUNNING, 0), else_=1),
                JobRunModel.created_at,
                JobRunModel.id,
            )
            .limit(1)
            .execution_options(populate_existing=True)
        )
        return None if model is None else to_domain(model)

    async def history(self, job_key: str, *, limit: int) -> list[JobRun]:
        """Read recent runs in stable descending creation order."""
        models = await self._session.scalars(
            select(JobRunModel)
            .where(JobRunModel.job_key == job_key)
            .order_by(JobRunModel.created_at.desc(), JobRunModel.id.desc())
            .limit(limit)
            .execution_options(populate_existing=True)
        )
        return [to_domain(model) for model in models]

    async def last_scheduled_for(self, job_key: str) -> datetime | None:
        """Exclude manual requests from the scheduled watermark."""
        return await self._session.scalar(
            select(func.max(JobRunModel.scheduled_for)).where(
                JobRunModel.job_key == job_key,
                JobRunModel.deduplication_key.is_not(None),
            )
        )

    async def worker_alive(
        self, since: datetime, *, worker_id: str | None = None
    ) -> bool:
        """Check independent worker heartbeats, including idle workers."""
        condition = exists().where(WorkerHeartbeatModel.heartbeat_at >= since)
        if worker_id is not None:
            condition = condition.where(WorkerHeartbeatModel.worker_id == worker_id)
        return bool(await self._session.scalar(select(condition)))
