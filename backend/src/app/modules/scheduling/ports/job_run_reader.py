"""JobRunReader driven port for durable scheduled work."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from app.modules.scheduling.domain.job_run import JobRun


class JobRunReader(Protocol):
    """Engine-independent operations on job-run data."""

    async def get(self, run_id: UUID) -> JobRun:
        """Return a run or raise UnknownRunError."""
        ...

    async def active_run(self, job_key: str) -> JobRun | None:
        """Return running work first, otherwise the oldest waiting run."""
        ...

    async def history(self, job_key: str, *, limit: int) -> list[JobRun]:
        """Return recent runs of one job, newest first."""
        ...

    async def last_scheduled_for(self, job_key: str) -> datetime | None:
        """Return the latest accepted scheduled occurrence, excluding manual runs."""
        ...

    async def worker_alive(
        self, since: datetime, *, worker_id: str | None = None
    ) -> bool:
        """Check a specific worker, or any worker, for liveness since the cutoff."""
        ...
