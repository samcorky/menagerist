"""In-memory execution recording with worker-ownership checks."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.job_run import utc_instant

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )
    from app.modules.scheduling.domain.job_run import RunStatus


class InMemoryJobRunRecorder:
    """Record immutable transitions and independently track idle workers."""

    def __init__(self, store: InMemorySchedulingStore) -> None:
        self._store = store

    async def heartbeat(self, run_id: UUID, worker_id: str, now: datetime) -> None:
        """Renew a run owned by this worker."""
        self._store.runs[run_id] = self._store.get(run_id).heartbeat(worker_id, now)

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
        self._store.runs[run_id] = self._store.get(run_id).finish(
            worker_id, status, now, error=error
        )

    async def reap_abandoned(self, older_than: datetime, now: datetime) -> int:
        """Abandon expired running jobs without requeueing them."""
        count = 0
        for run_id, run in self._store.runs.items():
            updated = run.abandon_if_stale(older_than, now)
            if updated is not run:
                self._store.runs[run_id] = updated
                count += 1
        return count

    async def worker_heartbeat(self, worker_id: str, now: datetime) -> None:
        """Keep the latest heartbeat if clocks or messages arrive out of order."""
        now = utc_instant(now)
        self._store.workers[worker_id] = max(
            now, self._store.workers.get(worker_id, now)
        )
