from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.scheduling.adapters.api.dependencies import (
    get_job_history_use_case,
    get_list_jobs_use_case,
    get_preview_schedule_use_case,
    get_run_job_now_use_case,
)
from app.modules.scheduling.adapters.api.schemas import (
    JobResponse,
    JobRunResponse,
    SchedulePreviewResponse,
)
from app.modules.scheduling.application.get_job_history import (
    GetJobHistory,
    GetJobHistoryQuery,
)
from app.modules.scheduling.application.list_jobs import ListJobs, ListJobsQuery
from app.modules.scheduling.application.preview_schedule import (
    MAX_PREVIEW_RUNS,
    PreviewSchedule,
    PreviewScheduleQuery,
)
from app.modules.scheduling.application.run_job_now import RunJobNow, RunJobNowCommand
from app.modules.scheduling.domain.errors import RunNowNotAllowedError, UnknownJobError
from app.platform.config import get_scheduler_settings
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError

router = APIRouter(
    prefix="/scheduling", tags=["Scheduling"], route_class=PermissionAwareRoute
)

_FORBIDDEN = error_response(
    ForbiddenError, detail="You do not have permission to view scheduled tasks."
)
_UNKNOWN_JOB = error_response(UnknownJobError, detail="No job is registered as 'x'.")
_NOT_RUNNABLE = error_response(
    RunNowNotAllowedError, detail="'x' cannot be run by hand."
)
_INVALID = error_response(ValidationError, detail="Invalid cron schedule: 61 * * * *")


@router.get(
    "/schedule-preview",
    response_model=SchedulePreviewResponse,
    operation_id="preview_schedule",
    responses={**_FORBIDDEN, **_INVALID},
)
async def preview_schedule(
    response: Response,
    use_case: Annotated[PreviewSchedule, Depends(get_preview_schedule_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    expression: Annotated[
        str,
        Query(
            max_length=200,
            description="A five-part cron expression. Empty means off.",
            examples=["0 3 * * *"],
        ),
    ] = "",
    count: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PREVIEW_RUNS,
            description="How many upcoming runs to return.",
        ),
    ] = 3,
) -> SchedulePreviewResponse:
    """Show when a schedule would next run, in the instance timezone.

    Read by the same engine the scheduler runs, so the times are the real ones.
    """
    response.headers["Cache-Control"] = "private, no-store"
    preview = await use_case.handle(
        PreviewScheduleQuery(
            expression=expression,
            timezone=get_scheduler_settings().timezone.key,
            now=datetime.now(UTC),
            count=count,
        ),
        actor,
    )
    return SchedulePreviewResponse.from_domain(preview)


@router.get(
    "/jobs",
    response_model=list[JobResponse],
    operation_id="list_jobs",
    responses={**_FORBIDDEN},
)
async def list_jobs(
    response: Response,
    use_case: Annotated[ListJobs, Depends(get_list_jobs_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> list[JobResponse]:
    """List every scheduled job with its schedule, next run and current work."""
    response.headers["Cache-Control"] = "private, no-store"
    statuses = await use_case.handle(
        ListJobsQuery(
            now=datetime.now(UTC), timezone=get_scheduler_settings().timezone.key
        ),
        actor,
    )
    return [JobResponse.from_domain(item) for item in statuses]


@router.get(
    "/jobs/{job_key}/runs",
    response_model=list[JobRunResponse],
    operation_id="list_job_runs",
    responses={**_FORBIDDEN, **_UNKNOWN_JOB},
)
async def list_job_runs(
    job_key: str,
    response: Response,
    use_case: Annotated[GetJobHistory, Depends(get_job_history_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
    limit: Annotated[
        int, Query(ge=1, le=100, description="How many recent runs to return.")
    ] = 20,
) -> list[JobRunResponse]:
    """Show a job's recent runs, newest first."""
    response.headers["Cache-Control"] = "private, no-store"
    runs = await use_case.handle(
        GetJobHistoryQuery(job_key=job_key, limit=limit), actor
    )
    return [JobRunResponse.from_domain(run) for run in runs]


@router.post(
    "/jobs/{job_key}/run",
    response_model=JobRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="run_job_now",
    responses={**_FORBIDDEN, **_UNKNOWN_JOB, **_NOT_RUNNABLE},
)
async def run_job_now(
    job_key: str,
    use_case: Annotated[RunJobNow, Depends(get_run_job_now_use_case)],
    actor: Annotated[Actor, Depends(get_current_actor)],
) -> JobRunResponse:
    """Queue a run for the worker to pick up.

    A run already waiting or in progress is returned instead of stacking another.
    """
    run = await use_case.handle(
        RunJobNowCommand(job_key=job_key, now=datetime.now(UTC)), actor
    )
    return JobRunResponse.from_domain(run)
