"""Portable job metadata contributed by each owning module."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum

from app.shared_kernel.errors import ValidationError


class Lane(StrEnum):
    """Independent worker capacity for ordinary and resource-heavy jobs."""

    DEFAULT = "default"
    HEAVY = "heavy"


class Overlap(StrEnum):
    """How enqueueing handles already queued or running work."""

    SKIP = "skip"
    COALESCE = "coalesce"
    QUEUE = "queue"


class MissedRun(StrEnum):
    """Whether to catch up the latest missed occurrence."""

    SKIP = "skip"
    RUN_ONCE = "run_once"


@dataclass(frozen=True, slots=True, kw_only=True, eq=False)
class JobDefinition:
    """Job policy without a handler, registry or engine dependency."""

    job_key: str
    lane: Lane = Lane.DEFAULT
    overlap: Overlap = Overlap.COALESCE
    missed_run: MissedRun = MissedRun.SKIP
    max_lateness: timedelta = timedelta(minutes=10)
    schedule_key: str | None = None
    run_now_allowed: bool = True
    needs_setup_complete: bool = True

    def __post_init__(self) -> None:
        """Reject unusable keys and catch-up windows."""
        if not self.job_key.strip():
            raise ValidationError("A job key is required")
        if self.max_lateness < timedelta():
            raise ValidationError("Maximum lateness cannot be negative")
