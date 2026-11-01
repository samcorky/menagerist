"""Shared storage behind the in-memory queue, reader and recorder."""

from copy import copy
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from app.modules.scheduling.domain.errors import UnknownRunError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.modules.scheduling.domain.schedule_cursor import ScheduleCursor


@dataclass(kw_only=True, eq=False)
class InMemorySchedulingStore:
    """Detached run entities and independent worker heartbeat timestamps."""

    runs: dict[UUID, JobRun] = field(default_factory=dict)
    workers: dict[str, datetime] = field(default_factory=dict)
    cursors: dict[str, ScheduleCursor] = field(default_factory=dict)

    def get(self, run_id: UUID) -> JobRun:
        """Return a stored snapshot or raise the scheduler's not-found error."""
        try:
            return copy(self.runs[run_id])
        except KeyError as exc:
            raise UnknownRunError(str(run_id)) from exc

    def active(self, job_key: str) -> list[JobRun]:
        """Return running work first, then queued work in creation order."""
        return sorted(
            (
                copy(run)
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

    def save(self, run: JobRun) -> None:
        """Store a detached copy so later caller mutations are not persisted."""
        self.runs[run.id] = copy(run)
