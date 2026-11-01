"""Portable overlap and claim policies used by every queue adapter."""

from typing import TYPE_CHECKING

from app.modules.scheduling.domain.job_run import JobRun, RunStatus, utc_instant
from app.shared_kernel.jobs import Overlap

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence
    from datetime import datetime
    from uuid import UUID

    from app.shared_kernel.jobs import Lane


def select_submission(
    run: JobRun,
    previous: JobRun | None,
    active: Sequence[JobRun],
    *,
    deduplicate_active: bool,
) -> JobRun:
    """Reuse accepted work and apply skip, coalesce or queue policy."""
    if previous is not None:
        return previous
    if active and (deduplicate_active or run.overlap is Overlap.SKIP):
        return next(
            (item for item in active if item.status is RunStatus.RUNNING), active[0]
        )
    if run.overlap is Overlap.COALESCE:
        queued = next(
            (item for item in active if item.status is RunStatus.QUEUED), None
        )
        if queued is not None:
            return queued
    return run


def next_claim(
    runs: Iterable[JobRun],
    lanes: Collection[Lane],
    now: datetime,
    *,
    run_id: UUID | None = None,
) -> JobRun | None:
    """Select the oldest due run, keeping executions of each job sequential."""
    now = utc_instant(now)
    rows = list(runs)
    running = {run.job_key for run in rows if run.status is RunStatus.RUNNING}
    eligible = (
        run
        for run in rows
        if run.status is RunStatus.QUEUED
        and run.lane in lanes
        and run.scheduled_for <= now
        and run.job_key not in running
        and (run_id is None or run.id == run_id)
    )
    return min(
        eligible,
        key=lambda run: (run.scheduled_for, run.created_at, run.id.int),
        default=None,
    )
