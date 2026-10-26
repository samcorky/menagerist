"""Read-side queries over in-memory scheduled work."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )
    from app.modules.scheduling.domain.job_run import JobRun


class InMemoryJobRunReader:
    """Expose the same history and liveness queries as the durable store."""

    def __init__(self, store: InMemorySchedulingStore) -> None:
        self._store = store

    async def get(self, run_id: UUID) -> JobRun:
        """Return a run or raise UnknownRunError."""
        return self._store.get(run_id)

    async def active_run(self, job_key: str) -> JobRun | None:
        """Return running work first, otherwise the oldest queued run."""
        active = self._store.active(job_key)
        return active[0] if active else None

    async def history(self, job_key: str, *, limit: int) -> list[JobRun]:
        """Return recent runs for the requested job only."""
        rows = (run for run in self._store.runs.values() if run.job_key == job_key)
        return sorted(rows, key=lambda run: (run.created_at, run.id.int), reverse=True)[
            :limit
        ]

    async def last_scheduled_for(self, job_key: str) -> datetime | None:
        """Return the latest accepted scheduled fire, excluding manual work."""
        return max(
            (
                run.scheduled_for
                for run in self._store.runs.values()
                if run.job_key == job_key and run.deduplication_key is not None
            ),
            default=None,
        )

    async def worker_alive(self, since: datetime) -> bool:
        """Look at worker heartbeats rather than inferring liveness from jobs."""
        return any(moment >= since for moment in self._store.workers.values())
