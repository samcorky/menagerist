"""Shared storage behind the in-memory queue, reader and recorder."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.scheduling.domain.errors import UnknownRunError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus


@dataclass(kw_only=True, eq=False)
class InMemorySchedulingStore:
    """Immutable run snapshots and independent worker heartbeat timestamps."""

    runs: dict[UUID, JobRun] = field(default_factory=dict)
    workers: dict[str, datetime] = field(default_factory=dict)

    def get(self, run_id: UUID) -> JobRun:
        """Return a stored snapshot or raise the scheduler's not-found error."""
        try:
            return self.runs[run_id]
        except KeyError as exc:
            raise UnknownRunError(str(run_id)) from exc

    def active(self, job_key: str) -> list[JobRun]:
        """Return running work first, then queued work in creation order."""
        return sorted(
            (
                run
                for run in self.runs.values()
                if run.job_key == job_key
                and run.status in {RunStatus.QUEUED, RunStatus.RUNNING}
            ),
            key=lambda run: (
                run.status is not RunStatus.RUNNING,
                run.created_at,
                run.id.int,
            ),
        )
