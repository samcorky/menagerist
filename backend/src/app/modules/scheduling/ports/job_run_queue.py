"""JobRunQueue driven port for durable scheduled work."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Collection
    from datetime import datetime

    from app.modules.scheduling.domain.job_run import JobRun
    from app.shared_kernel.jobs import Lane


class JobRunQueue(Protocol):
    """Engine-independent operations on job-run data."""

    async def enqueue(self, run: JobRun, *, deduplicate_active: bool = False) -> JobRun:
        """Enqueue in the caller's transaction, applying deduplication and overlap."""
        ...

    async def claim(
        self, lanes: Collection[Lane], worker_id: str, now: datetime
    ) -> JobRun | None:
        """Atomically claim the oldest eligible queued run for a worker."""
        ...
