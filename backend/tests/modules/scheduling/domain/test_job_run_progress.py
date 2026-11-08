"""A running job keeps its latest progress; a success drops it, a failure keeps it."""

from datetime import UTC, datetime

import pytest

from app.modules.scheduling.domain.errors import LostClaimError
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.progress import ProgressSnapshot

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
SNAPSHOT = ProgressSnapshot(phases=(), message=None, percent=40, outcome="running")


def running() -> JobRun:
    """A run claimed by `worker`."""
    run = JobRun.create(job_key="backup.create", scheduled_for=NOW)
    run.start("worker", NOW)
    return run


def test_a_new_run_has_no_progress() -> None:
    """Progress appears only once a job reports it."""
    assert JobRun.create(job_key="x", scheduled_for=NOW).progress is None


def test_the_claimant_records_progress() -> None:
    """The owner of a running job keeps its latest snapshot."""
    run = running()
    run.record_progress("worker", SNAPSHOT)
    assert run.progress is SNAPSHOT


def test_another_worker_cannot_record_progress() -> None:
    """A foreign worker is refused, as for a heartbeat."""
    run = running()
    with pytest.raises(LostClaimError):
        run.record_progress("intruder", SNAPSHOT)
    assert run.progress is None


def test_a_queued_run_cannot_record_progress() -> None:
    """Only running work reports."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    with pytest.raises(LostClaimError):
        run.record_progress("worker", SNAPSHOT)


def test_success_drops_the_progress() -> None:
    """Progress is ephemeral; only the final state is durable."""
    run = running()
    run.record_progress("worker", SNAPSHOT)
    run.finish("worker", RunStatus.SUCCEEDED, NOW)
    assert run.progress is None


def test_failure_keeps_where_the_job_stopped() -> None:
    """A failed run shows its last phase and counts."""
    run = running()
    run.record_progress("worker", SNAPSHOT)
    run.finish("worker", RunStatus.FAILED, NOW, error="boom")
    assert run.progress is SNAPSHOT


def test_abandonment_keeps_the_last_snapshot() -> None:
    """A crashed worker's run still shows how far it got."""
    run = running()
    run.record_progress("worker", SNAPSHOT)
    run.abandon(NOW)
    assert run.progress is SNAPSHOT
