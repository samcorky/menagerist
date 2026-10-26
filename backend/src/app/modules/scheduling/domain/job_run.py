"""Immutable job-run state and execution ownership."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import NAMESPACE_URL, UUID, uuid5, uuid7

from app.modules.scheduling.domain.errors import (
    InvalidRunTransitionError,
    LostClaimError,
)
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap


def utc_instant(moment: datetime) -> datetime:
    """Require an aware timestamp and normalise DST folds to UTC."""
    if moment.utcoffset() is None:
        raise ValidationError("Timezone-aware datetimes are required")
    return moment.astimezone(UTC)


class RunStatus(StrEnum):
    """Persisted job-run lifecycle."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    ABANDONED = "abandoned"


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class JobRun:
    """A queued occurrence and its successive execution snapshots."""

    job_key: str
    scheduled_for: datetime
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    lane: Lane = Lane.DEFAULT
    overlap: Overlap = Overlap.COALESCE
    deduplication_key: UUID | None = None
    requested_by: UUID | None = None
    status: RunStatus = RunStatus.QUEUED
    worker_id: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        """Store schedule instants in UTC so DST folds compare correctly."""
        object.__setattr__(self, "scheduled_for", utc_instant(self.scheduled_for))

    @classmethod
    def for_schedule(cls, job: JobDefinition, fire: datetime) -> JobRun:
        """Create a fresh UUID7 run with a stable key for its scheduled occurrence."""
        fire = utc_instant(fire)
        return cls(
            job_key=job.job_key,
            lane=job.lane,
            overlap=job.overlap,
            scheduled_for=fire,
            deduplication_key=uuid5(
                NAMESPACE_URL, f"menagerist:{job.job_key}:{fire.isoformat()}"
            ),
        )

    def start(self, worker_id: str, now: datetime) -> JobRun:
        """Claim a due queued run for one worker."""
        now = utc_instant(now)
        if self.status is not RunStatus.QUEUED or now < self.scheduled_for:
            raise InvalidRunTransitionError("Only a due queued run can start")
        return replace(
            self,
            status=RunStatus.RUNNING,
            worker_id=worker_id,
            started_at=now,
            heartbeat_at=now,
        )

    def _assert_owner(self, worker_id: str) -> None:
        if self.status is not RunStatus.RUNNING or self.worker_id != worker_id:
            raise LostClaimError("The worker does not own this running job")

    def heartbeat(self, worker_id: str, now: datetime) -> JobRun:
        """Renew the claimant's heartbeat without moving its timestamp backwards."""
        self._assert_owner(worker_id)
        now = utc_instant(now)
        return replace(self, heartbeat_at=max(now, self.heartbeat_at or now))

    def finish(
        self,
        worker_id: str,
        status: RunStatus,
        now: datetime,
        *,
        error: str | None = None,
    ) -> JobRun:
        """Record the claimant's execution result."""
        self._assert_owner(worker_id)
        if status not in {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.SKIPPED}:
            raise InvalidRunTransitionError(
                "Execution must finish with a terminal outcome"
            )
        return replace(self, status=status, finished_at=utc_instant(now), error=error)

    def abandon(self, now: datetime) -> JobRun:
        """Fence a crashed worker; abandoned work is never implicitly retried."""
        if self.status is not RunStatus.RUNNING:
            raise InvalidRunTransitionError("Only a running job can be abandoned")
        return replace(
            self,
            status=RunStatus.ABANDONED,
            finished_at=utc_instant(now),
            error="heartbeat_expired",
        )

    def abandon_if_stale(self, older_than: datetime, now: datetime) -> JobRun:
        """Return an abandoned snapshot only when the running heartbeat expired."""
        older_than = utc_instant(older_than)
        if (
            self.status is RunStatus.RUNNING
            and self.heartbeat_at is not None
            and self.heartbeat_at < older_than
        ):
            return self.abandon(now)
        return self
