"""A run's progress survives the trip between the entity and its JSONB column."""

from datetime import UTC, datetime

from app.modules.scheduling.adapters.api.schemas import JobRunResponse
from app.modules.scheduling.adapters.persistence.job_run_mapping import (
    apply_transition,
    to_domain,
    to_model,
)
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.progress import PhaseState, ProgressSnapshot

NOW = datetime(2026, 11, 7, 12, tzinfo=UTC)
SNAPSHOT = ProgressSnapshot(
    phases=(
        PhaseState(
            key="verify",
            label="Checking the new backup",
            state="done",
            done=9,
            total=9,
            unit="bytes",
        ),
        PhaseState(
            key="media",
            label="Saving photos and files",
            state="running",
            done=3,
            total=10,
        ),
    ),
    message=None,
    percent=55,
    outcome="running",
)


def test_progress_round_trips_through_the_row() -> None:
    """The column holds plain JSON and rebuilds the same snapshot."""
    run = JobRun.create(job_key="backup.create", scheduled_for=NOW)
    run.start("worker", NOW)
    run.record_progress("worker", SNAPSHOT)
    model = to_model(run)
    assert isinstance(model.progress, dict)
    assert model.progress["percent"] == 55
    assert to_domain(model).progress == SNAPSHOT


def test_a_run_without_progress_stores_null() -> None:
    """Nothing reported means a null column."""
    model = to_model(JobRun.create(job_key="x", scheduled_for=NOW))
    assert model.progress is None
    assert to_domain(model).progress is None


def test_a_transition_writes_and_clears_the_column() -> None:
    """Applying a success clears what an earlier write stored."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    run.start("worker", NOW)
    model = to_model(run)
    run.record_progress("worker", SNAPSHOT)
    apply_transition(model, run)
    assert model.progress == SNAPSHOT.to_dict()
    run.finish("worker", RunStatus.SUCCEEDED, NOW)
    apply_transition(model, run)
    assert model.progress is None


def test_the_response_carries_the_progress() -> None:
    """A running job's phases reach the interface."""
    run = JobRun.create(job_key="backup.create", scheduled_for=NOW)
    run.start("worker", NOW)
    run.record_progress("worker", SNAPSHOT)
    body = JobRunResponse.from_domain(run).model_dump(mode="json")
    assert body["progress"]["percent"] == 55
    assert [phase["key"] for phase in body["progress"]["phases"]] == [
        "verify",
        "media",
    ]
    assert body["progress"]["phases"][0]["unit"] == "bytes"


def test_a_run_without_progress_serialises_null() -> None:
    """The field is always present, and null when there is nothing to show."""
    run = JobRun.create(job_key="x", scheduled_for=NOW)
    assert JobRunResponse.from_domain(run).model_dump(mode="json")["progress"] is None
