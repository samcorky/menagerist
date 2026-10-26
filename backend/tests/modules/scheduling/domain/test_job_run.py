"""Job definitions and immutable run transitions."""

from datetime import UTC, datetime, timedelta
from uuid import uuid7
from zoneinfo import ZoneInfo

import pytest

from app.modules.scheduling.domain.errors import (
    InvalidRunTransitionError,
    LostClaimError,
)
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.jobs import JobDefinition, Lane, Overlap

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def test_scheduled_deduplication_key_is_stable_across_timezones() -> None:
    """Scheduled occurrences deduplicate while keeping UUID7 primary keys."""
    job = JobDefinition(job_key="backup.create", lane=Lane.HEAVY)
    first = JobRun.for_schedule(job, NOW)
    second = JobRun.for_schedule(job, NOW.astimezone(ZoneInfo("America/New_York")))
    assert first.id.version == 7
    assert first.id != second.id
    assert first.deduplication_key == second.deduplication_key
    assert (
        first.deduplication_key
        != JobRun.for_schedule(job, NOW + timedelta(minutes=1)).deduplication_key
    )
    assert (
        first.deduplication_key
        != JobRun.for_schedule(JobDefinition(job_key="other"), NOW).deduplication_key
    )
    assert first.lane is Lane.HEAVY
    assert first.scheduled_for == NOW


@pytest.mark.parametrize("bad", [datetime(2026, 1, 1)])
def test_run_rejects_naive_schedule(bad: datetime) -> None:
    """Every queued occurrence identifies an absolute instant."""
    with pytest.raises(ValidationError):
        JobRun(job_key="backup.create", scheduled_for=bad)


def test_manual_run_and_successful_lifecycle() -> None:
    """Transitions preserve the queued snapshot and retain execution ownership."""
    requester = uuid7()
    queued = JobRun(job_key="backup.create", scheduled_for=NOW, requested_by=requester)
    running = queued.start("worker-a", NOW)
    heartbeat = running.heartbeat("worker-a", NOW + timedelta(seconds=10))
    finished = heartbeat.finish(
        "worker-a", RunStatus.SUCCEEDED, NOW + timedelta(seconds=20)
    )
    assert queued.status is RunStatus.QUEUED
    assert queued.deduplication_key is None
    assert running.started_at == NOW
    assert running.worker_id == "worker-a"
    assert heartbeat.heartbeat_at == NOW + timedelta(seconds=10)
    assert finished.status is RunStatus.SUCCEEDED
    assert finished.finished_at == NOW + timedelta(seconds=20)
    assert finished.requested_by == requester
    assert finished.error is None


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.SKIPPED])
def test_terminal_outcomes_preserve_the_reason(status: RunStatus) -> None:
    """Failures and skips retain their diagnostic reason."""
    run = JobRun(job_key="x", scheduled_for=NOW).start("worker", NOW)
    result = run.finish("worker", status, NOW, error="reason")
    assert result.status is status
    assert result.error == "reason"


def test_abandoned_runs_are_terminal_and_stale_workers_cannot_finish() -> None:
    """Reaping fences a late completion without implicitly retrying the job."""
    run = JobRun(job_key="x", scheduled_for=NOW).start("worker", NOW)
    abandoned = run.abandon(NOW + timedelta(minutes=5))
    assert abandoned.status is RunStatus.ABANDONED
    assert abandoned.error == "heartbeat_expired"
    with pytest.raises(LostClaimError):
        abandoned.finish("worker", RunStatus.SUCCEEDED, NOW + timedelta(minutes=6))
    with pytest.raises(LostClaimError):
        abandoned.heartbeat("worker", NOW + timedelta(minutes=6))


def test_invalid_transitions_and_foreign_workers_are_rejected() -> None:
    """A queued run starts once, and only its claimant may update it."""
    run = JobRun(job_key="x", scheduled_for=NOW)
    with pytest.raises(InvalidRunTransitionError):
        run.start("worker", NOW - timedelta(seconds=1))
    running = run.start("worker", NOW)
    with pytest.raises(InvalidRunTransitionError):
        running.start("worker", NOW)
    for status in [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.ABANDONED]:
        with pytest.raises(InvalidRunTransitionError):
            running.finish("worker", status, NOW)
    with pytest.raises(LostClaimError):
        running.heartbeat("other", NOW)
    with pytest.raises(LostClaimError):
        running.finish("other", RunStatus.SUCCEEDED, NOW)
    with pytest.raises(InvalidRunTransitionError):
        run.abandon(NOW)


def test_heartbeat_time_never_moves_backwards() -> None:
    """Clock skew must not make a healthy run appear older."""
    run = JobRun(job_key="x", scheduled_for=NOW).start("worker", NOW)
    assert run.heartbeat("worker", NOW - timedelta(minutes=1)).heartbeat_at == NOW


@pytest.mark.parametrize(
    ("key", "lateness"), [("", timedelta()), ("x", timedelta(seconds=-1))]
)
def test_invalid_job_definitions(key: str, lateness: timedelta) -> None:
    """Definitions reject missing keys and negative catch-up windows."""
    with pytest.raises(ValidationError):
        JobDefinition(job_key=key, max_lateness=lateness)


def test_job_definition_defaults_and_policy_override() -> None:
    """Definitions carry portable metadata without handler or engine references."""
    job = JobDefinition(
        job_key="backup.create",
        lane=Lane.HEAVY,
        overlap=Overlap.SKIP,
        schedule_key="backup.schedule",
    )
    assert job.lane is Lane.HEAVY
    assert job.overlap is Overlap.SKIP
    assert job.schedule_key == "backup.schedule"
    assert job.run_now_allowed
    assert job.needs_setup_complete
