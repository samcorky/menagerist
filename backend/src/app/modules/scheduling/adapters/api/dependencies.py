"""Wire the scheduling API to its use cases."""

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.application.preview_schedule import PreviewSchedule

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard


def get_preview_schedule_use_case(
    guard: Annotated[AccessGuard, Depends(get_access_guard)],
) -> PreviewSchedule:
    return PreviewSchedule(CronScheduleEvaluator(), guard)
