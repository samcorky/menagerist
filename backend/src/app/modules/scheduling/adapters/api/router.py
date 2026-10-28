from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.entrypoints.api.shared.dependencies import get_current_actor
from app.entrypoints.api.shared.http.problem_response import error_response
from app.entrypoints.api.shared.permission_aware_route import PermissionAwareRoute
from app.modules.scheduling.adapters.api.dependencies import (
    get_preview_schedule_use_case,
)
from app.modules.scheduling.adapters.api.schemas import SchedulePreviewResponse
from app.modules.scheduling.application.preview_schedule import (
    MAX_PREVIEW_RUNS,
    PreviewSchedule,
    PreviewScheduleQuery,
)
from app.platform.config import get_scheduler_settings
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError

router = APIRouter(
    prefix="/scheduling", tags=["Scheduling"], route_class=PermissionAwareRoute
)

_FORBIDDEN = error_response(
    ForbiddenError, detail="You do not have permission to view scheduled tasks."
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
