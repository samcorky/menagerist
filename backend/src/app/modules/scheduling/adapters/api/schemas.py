"""Response bodies for the scheduling API."""

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.scheduling.application.list_jobs import JobStatus  # noqa: TC001
from app.modules.scheduling.application.preview_schedule import SchedulePreview  # noqa: TC001
from app.modules.scheduling.domain.job_run import JobRun, RunStatus
from app.shared_kernel.jobs import Lane, MissedRun, Overlap

if TYPE_CHECKING:
    from pydantic.config import JsonDict


class SchedulePreviewResponse(BaseModel):
    """When a schedule would next run."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "timezone": "Europe/London",
                    "runs": [
                        "2026-10-29T03:00:00Z",
                        "2026-10-30T03:00:00Z",
                        "2026-10-31T03:00:00Z",
                    ],
                }
            ]
        }
    )

    timezone: str = Field(
        description="The instance timezone the schedule is read in (an IANA name)."
    )
    runs: list[datetime] = Field(
        description="The next runs as UTC instants, soonest first. Empty when off."
    )

    @classmethod
    def from_domain(cls, preview: SchedulePreview) -> SchedulePreviewResponse:
        """Build the response for a preview."""
        return cls(timezone=preview.timezone, runs=preview.runs)


RUN_EXAMPLE: JsonDict = {
    "id": "0198f3a2-7c1e-7a4b-9d2e-5b6c8f1a2b3c",
    "job_key": "backup.create",
    "status": "succeeded",
    "scheduled_for": "2026-10-28T03:00:00Z",
    "created_at": "2026-10-28T03:00:00Z",
    "started_at": "2026-10-28T03:00:02Z",
    "finished_at": "2026-10-28T03:01:10Z",
    "error": None,
    "requested_by": None,
}


def _humanise(job_key: str) -> str:
    """A readable fallback for a job whose module supplied no title."""
    words = job_key.rsplit(".", 1)[-1].replace("_", " ").replace("-", " ").strip()
    return words[:1].upper() + words[1:]


class JobRunResponse(BaseModel):
    """One execution of a job."""

    model_config = ConfigDict(json_schema_extra={"examples": [RUN_EXAMPLE]})

    id: UUID
    job_key: str
    status: RunStatus
    scheduled_for: datetime = Field(
        description="The occurrence this run was created for, or when it was requested."
    )
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error: str | None = Field(
        default=None, description="Why the run failed, when it did."
    )
    requested_by: UUID | None = Field(
        default=None, description="The administrator who ran it, when run by hand."
    )

    @classmethod
    def from_domain(cls, run: JobRun) -> JobRunResponse:
        """Build the response for a run."""
        return cls(
            id=run.id,
            job_key=run.job_key,
            status=run.status,
            scheduled_for=run.scheduled_for,
            created_at=run.created_at,
            started_at=run.started_at,
            finished_at=run.finished_at,
            error=run.error,
            requested_by=run.requested_by,
        )


class JobResponse(BaseModel):
    """A registered job with its effective schedule and current work."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "job_key": "backup.create",
                    "title": "Back up everything",
                    "description": "Saves a full copy of your collection.",
                    "lane": "heavy",
                    "overlap": "coalesce",
                    "missed_run": "run_once",
                    "run_now_allowed": True,
                    "schedule": "0 3 * * *",
                    "next_run_at": "2026-10-29T03:00:00Z",
                    "active_run": {
                        **RUN_EXAMPLE,
                        "status": "running",
                        "finished_at": None,
                    },
                }
            ]
        }
    )

    job_key: str
    title: str = Field(description="What the task is called, in plain language.")
    description: str = Field(description="What the task does, in a sentence.")
    lane: Lane
    overlap: Overlap
    missed_run: MissedRun
    run_now_allowed: bool
    schedule: str | None = Field(
        description="The effective cron expression, or null when off or unscheduled."
    )
    next_run_at: datetime | None = Field(
        description="When it next fires, or null when it has no schedule."
    )
    active_run: JobRunResponse | None = Field(
        description="The run in progress, or the oldest one waiting."
    )

    @classmethod
    def from_domain(cls, status: JobStatus) -> JobResponse:
        """Build the response for a job's status."""
        job = status.definition
        return cls(
            job_key=job.job_key,
            title=job.title or _humanise(job.job_key),
            description=job.description,
            lane=job.lane,
            overlap=job.overlap,
            missed_run=job.missed_run,
            run_now_allowed=job.run_now_allowed,
            schedule=status.expression,
            next_run_at=status.next_run_at,
            active_run=(
                JobRunResponse.from_domain(status.active_run)
                if status.active_run
                else None
            ),
        )
