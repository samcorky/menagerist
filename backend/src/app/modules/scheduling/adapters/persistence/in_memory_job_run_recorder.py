"""In-memory execution recording with worker-ownership checks."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.job_run import RunStatus, utc_instant

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )


class InMemoryJobRunRecorder:
    """Persist entity transitions and independently track idle workers."""

    def __init__(self, store: InMemorySchedulingStore) -> None:
        self._store = store

    async def prune_history(self, *, keep_per_job: int) -> int:
        """Retain completed history independently of active runs and cursors."""
        counts: dict[str, int] = {}
        removed = 0
        for run in sorted(
            self._store.runs.values(),
            key=lambda run: (run.created_at, run.id.int),
            reverse=True,
        ):
            if run.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                continue
            counts[run.job_key] = counts.get(run.job_key, 0) + 1
            if counts[run.job_key] > keep_per_job:
                del self._store.runs[run.id]
                removed += 1
        return removed

    async def heartbeat(self, run_id: UUID, worker_id: str, now: datetime) -> None:
        """Renew a run owned by this worker."""
        run = self._store.get(run_id)
        run.heartbeat(worker_id, now)
        self._store.save(run)

    async def finish(
        self,
        run_id: UUID,
        worker_id: str,
        status: RunStatus,
        now: datetime,
        *,
        error: str | None = None,
    ) -> None:
        """Persist an owned terminal result."""
        run = self._store.get(run_id)
        run.finish(worker_id, status, now, error=error)
        self._store.save(run)

    async def reap_abandoned(self, older_than: datetime, now: datetime) -> int:
        """Abandon expired running jobs without requeueing them."""
        count = 0
        for run_id in self._store.runs:
            run = self._store.get(run_id)
            if run.abandon_if_stale(older_than, now):
                self._store.save(run)
                count += 1
        return count

    async def worker_heartbeat(self, worker_id: str, now: datetime) -> None:
        """Keep the latest heartbeat if clocks or messages arrive out of order."""
        now = utc_instant(now)
        self._store.workers[worker_id] = max(
            now, self._store.workers.get(worker_id, now)
        )
