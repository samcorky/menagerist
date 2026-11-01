"""Detached mappings between execution rows and domain entities."""

from app.modules.scheduling.adapters.persistence.models import JobRunModel
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.jobs import Lane, Overlap


def to_domain(model: JobRunModel) -> JobRun:
    """Build an independent entity snapshot from a persisted row."""
    return JobRun(
        id=model.id,
        job_key=model.job_key,
        scheduled_for=model.scheduled_for,
        created_at=model.created_at,
        lane=Lane(model.lane),
        overlap=Overlap(model.overlap),
        deduplication_key=model.deduplication_key,
        requested_by=model.requested_by,
        status=RunStatus(model.status),
        worker_id=model.worker_id,
        started_at=model.started_at,
        heartbeat_at=model.heartbeat_at,
        finished_at=model.finished_at,
        error=model.error,
    )


def to_model(run: JobRun) -> JobRunModel:
    """Copy a domain-created occurrence into a new ORM row."""
    return JobRunModel(
        id=run.id,
        job_key=run.job_key,
        scheduled_for=run.scheduled_for,
        created_at=run.created_at,
        lane=run.lane.value,
        overlap=run.overlap.value,
        deduplication_key=run.deduplication_key,
        requested_by=run.requested_by,
        status=run.status.value,
        worker_id=run.worker_id,
        started_at=run.started_at,
        heartbeat_at=run.heartbeat_at,
        finished_at=run.finished_at,
        error=run.error,
    )


def apply_transition(model: JobRunModel, run: JobRun) -> None:
    """Persist only fields changed by lifecycle transitions."""
    model.status = run.status.value
    model.worker_id = run.worker_id
    model.started_at = run.started_at
    model.heartbeat_at = run.heartbeat_at
    model.finished_at = run.finished_at
    model.error = run.error
