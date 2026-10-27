"""Claimant-fenced lifecycle updates and independent worker heartbeats."""

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert

from app.modules.scheduling.adapters.persistence.job_run_mapping import (
    apply_transition,
    to_domain,
)
from app.modules.scheduling.adapters.persistence.models import (
    JobRunModel,
    WorkerHeartbeatModel,
)
from app.modules.scheduling.domain.errors import UnknownRunError
from app.modules.scheduling.domain.job_run import RunStatus, utc_instant

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncSession


class SqlAlchemyJobRunRecorder:
    """Lock the latest row before applying domain lifecycle rules."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def prune_history(self, *, keep_per_job: int) -> int:
        """Delete excess terminal rows without touching queue or cursor state."""
        ranked = (
            select(
                JobRunModel.id,
                func.row_number()
                .over(
                    partition_by=JobRunModel.job_key,
                    order_by=(JobRunModel.created_at.desc(), JobRunModel.id.desc()),
                )
                .label("position"),
            )
            .where(JobRunModel.status.not_in((RunStatus.QUEUED, RunStatus.RUNNING)))
            .subquery()
        )
        removed = await self._session.scalars(
            delete(JobRunModel)
            .where(
                JobRunModel.id.in_(
                    select(ranked.c.id).where(ranked.c.position > keep_per_job)
                )
            )
            .returning(JobRunModel.id)
            .execution_options(synchronize_session=False)
        )
        return len(removed.all())

    async def _locked(self, run_id: UUID) -> JobRunModel:
        model = await self._session.scalar(
            select(JobRunModel)
            .where(JobRunModel.id == run_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if model is None:
            raise UnknownRunError(str(run_id))
        return model

    async def heartbeat(self, run_id: UUID, worker_id: str, now: datetime) -> None:
        """Renew only the current claimant without regressing its heartbeat."""
        model = await self._locked(run_id)
        run = to_domain(model)
        run.heartbeat(worker_id, now)
        apply_transition(model, run)
        await self._session.flush()

    async def finish(
        self,
        run_id: UUID,
        worker_id: str,
        status: RunStatus,
        now: datetime,
        *,
        error: str | None = None,
    ) -> None:
        """Record a terminal outcome only while this worker still owns the run."""
        model = await self._locked(run_id)
        run = to_domain(model)
        run.finish(worker_id, status, now, error=error)
        apply_transition(model, run)
        await self._session.flush()

    async def reap_abandoned(self, older_than: datetime, now: datetime) -> int:
        """Fence expired claimants without waiting on another recorder."""
        models = await self._session.scalars(
            select(JobRunModel)
            .where(
                JobRunModel.status == RunStatus.RUNNING,
                JobRunModel.heartbeat_at < utc_instant(older_than),
            )
            .with_for_update(skip_locked=True)
            .execution_options(populate_existing=True)
        )
        count = 0
        for model in models:
            run = to_domain(model)
            if run.abandon_if_stale(older_than, now):
                apply_transition(model, run)
                count += 1
        await self._session.flush()
        return count

    async def worker_heartbeat(self, worker_id: str, now: datetime) -> None:
        """Upsert a worker's greatest observed heartbeat."""
        now = utc_instant(now)
        await self._session.execute(
            insert(WorkerHeartbeatModel)
            .values(worker_id=worker_id, heartbeat_at=now)
            .on_conflict_do_update(
                index_elements=[WorkerHeartbeatModel.worker_id],
                set_={
                    "heartbeat_at": func.greatest(
                        WorkerHeartbeatModel.heartbeat_at, now
                    )
                },
            )
        )
