"""Job definitions and mutable run-entity transitions."""

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
        JobRun.create(job_key="backup.create", scheduled_for=bad)


def test_manual_run_and_successful_lifecycle() -> None:
    """Entity methods update execution state while retaining requester and identity."""
    requester = uuid7()
    run = JobRun.create(
        job_key="backup.create", scheduled_for=NOW, requested_by=requester
    )
    run.start("worker-a", NOW)
    assert (run.status, run.started_at, run.worker_id) == (
        RunStatus.RUNNING,
        NOW,
        "worker-a",
    )
    assert run.deduplication_key is None
    run.heartbeat("worker-a", NOW + timedelta(seconds=10))
    assert run.heartbeat_at == NOW + timedelta(seconds=10)
    run.finish("worker-a", RunStatus.SUCCEEDED, NOW + timedelta(seconds=20))
    assert run.status is RunStatus.SUCCEEDED
    assert run.finished_at == NOW + timedelta(seconds=20)
    assert run.requested_by == requester
    assert run.error is None


@pytest.mark.parametrize("status", [RunStatus.FAILED, RunStatus.SKIPPED])
def test_terminal_outcomes_preserve_the_reason(status: RunStatus) -> None:
    """Failures and skips retain their diagnostic reason."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    run.start("worker", NOW)
    run.finish("worker", status, NOW, error="reason")
    assert run.status is status
    assert run.error == "reason"


def test_abandoned_runs_are_terminal_and_stale_workers_cannot_finish() -> None:
    """Reaping fences a late completion without implicitly retrying the job."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    run.start("worker", NOW)
    run.abandon(NOW + timedelta(minutes=5))
    assert run.status is RunStatus.ABANDONED
    assert run.error == "heartbeat_expired"
    with pytest.raises(LostClaimError):
        run.finish("worker", RunStatus.SUCCEEDED, NOW + timedelta(minutes=6))
    with pytest.raises(LostClaimError):
        run.heartbeat("worker", NOW + timedelta(minutes=6))


def test_invalid_transitions_and_foreign_workers_are_rejected() -> None:
    """A queued run starts once, and only its claimant may update it."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    with pytest.raises(InvalidRunTransitionError):
        run.start("worker", NOW - timedelta(seconds=1))
    with pytest.raises(InvalidRunTransitionError):
        run.abandon(NOW)
    run.start("worker", NOW)
    with pytest.raises(InvalidRunTransitionError):
        run.start("worker", NOW)
    for status in [RunStatus.QUEUED, RunStatus.RUNNING, RunStatus.ABANDONED]:
        with pytest.raises(InvalidRunTransitionError):
            run.finish("worker", status, NOW)
    with pytest.raises(LostClaimError):
        run.heartbeat("other", NOW)
    with pytest.raises(LostClaimError):
        run.finish("other", RunStatus.SUCCEEDED, NOW)


def test_heartbeat_time_never_moves_backwards() -> None:
    """Clock skew must not make a healthy run appear older."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    run.start("worker", NOW)
    run.heartbeat("worker", NOW - timedelta(minutes=1))
    assert run.heartbeat_at == NOW


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


def test_job_run_uses_the_shared_identity_mixin() -> None:
    """Scheduler runs participate in the same identity contract as other entities."""
    from app.shared_kernel.mixins import Identifiable

    run = JobRun.create(job_key="x", scheduled_for=NOW)
    assert isinstance(run, Identifiable)
    assert run.id.version == 7
