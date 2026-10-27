"""Transactional Postgres submissions and non-blocking claims."""

from copy import copy
from typing import TYPE_CHECKING

from sqlalchemy import exists, or_, select, true
from sqlalchemy.orm import aliased

from app.modules.scheduling.adapters.persistence.job_lock import lock_job, try_lock_job
from app.modules.scheduling.adapters.persistence.job_run_mapping import (
    apply_transition,
    to_domain,
    to_model,
)
from app.modules.scheduling.adapters.persistence.models import JobRunModel
from app.modules.scheduling.domain.job_run import RunStatus, utc_instant
from app.modules.scheduling.domain.queue_policy import select_submission

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.modules.scheduling.domain.job_run import JobRun
    from app.shared_kernel.jobs import Lane


class SqlAlchemyJobRunQueue:
    """Join the caller's transaction; never commit inside an adapter."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, run: JobRun, *, deduplicate_active: bool = False) -> JobRun:
        """Serialise per-job policy decisions, including an initially empty queue."""
        await lock_job(self._session, run.job_key)
        predicate = JobRunModel.id == run.id
        if run.deduplication_key is not None:
            predicate = or_(
                predicate, JobRunModel.deduplication_key == run.deduplication_key
            )
        previous = await self._session.scalar(
            select(JobRunModel)
            .where(predicate)
            .execution_options(populate_existing=True)
        )
        active = await self._session.scalars(
            select(JobRunModel)
            .where(
                JobRunModel.job_key == run.job_key,
                JobRunModel.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
            )
            .order_by(JobRunModel.created_at, JobRunModel.id)
            .execution_options(populate_existing=True)
        )
        selected = select_submission(
            run,
            None if previous is None else to_domain(previous),
            [to_domain(model) for model in active],
            deduplicate_active=deduplicate_active,
        )
        if selected is run:
            self._session.add(to_model(run))
            await self._session.flush()
        return copy(selected)

    async def claim(
        self,
        lanes: Collection[Lane],
        worker_id: str,
        now: datetime,
        *,
        run_id: UUID | None = None,
    ) -> JobRun | None:
        """Skip locked rows and jobs, then recheck per-job exclusion after locking."""
        now = utc_instant(now)
        skipped: set[str] = set()
        running = aliased(JobRunModel)
        while True:
            model = await self._session.scalar(
                select(JobRunModel)
                .where(
                    JobRunModel.status == RunStatus.QUEUED,
                    true() if run_id is None else JobRunModel.id == run_id,
                    JobRunModel.lane.in_(lanes),
                    JobRunModel.scheduled_for <= now,
                    JobRunModel.job_key.not_in(skipped),
                    ~exists().where(
                        running.job_key == JobRunModel.job_key,
                        running.status == RunStatus.RUNNING,
                    ),
                )
                .order_by(
                    JobRunModel.scheduled_for, JobRunModel.created_at, JobRunModel.id
                )
                .limit(1)
                .with_for_update(skip_locked=True)
                .execution_options(populate_existing=True)
            )
            if model is None:
                return None
            skipped.add(model.job_key)
            if not await try_lock_job(self._session, model.job_key):
                continue
            if await self._session.scalar(
                select(
                    exists().where(
                        JobRunModel.job_key == model.job_key,
                        JobRunModel.status == RunStatus.RUNNING,
                    )
                )
            ):
                continue
            run = to_domain(model)
            run.start(worker_id, now)
            apply_transition(model, run)
            await self._session.flush()
            return run
