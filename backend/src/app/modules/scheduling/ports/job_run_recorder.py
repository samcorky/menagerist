"""JobRunRecorder driven port for durable scheduled work."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from app.modules.scheduling.domain.job_run import RunStatus


class JobRunRecorder(Protocol):
    """Engine-independent operations on job-run data."""

    async def prune_history(self, *, keep_per_job: int) -> int:
        """Keep the newest N terminal runs per job, ordered by creation and id."""
        ...

    async def heartbeat(self, run_id: UUID, worker_id: str, now: datetime) -> None:
        """Renew a running job only for its current claimant."""
        ...

    async def finish(
        self,
        run_id: UUID,
        worker_id: str,
        status: RunStatus,
        now: datetime,
        *,
        error: str | None = None,
    ) -> None:
        """Record a claimant's success, failure or skip."""
        ...

    async def reap_abandoned(self, older_than: datetime, now: datetime) -> int:
        """Abandon expired running work, without implicitly retrying it."""
        ...

    async def worker_heartbeat(self, worker_id: str, now: datetime) -> None:
        """Report worker liveness even when no job is running."""
        ...
