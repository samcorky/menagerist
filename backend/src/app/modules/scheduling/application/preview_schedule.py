"""Show when a schedule would next run, for someone editing it."""

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar

from app.modules.scheduling.application.permissions import SchedulingPermission
from app.modules.scheduling.domain.job_run import utc_instant
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase
from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

MAX_PREVIEW_RUNS = 10


@dataclass(frozen=True, kw_only=True)
class PreviewScheduleQuery:
    """The expression to read, the instance zone and the instant to count from."""

    expression: str
    timezone: str
    now: datetime
    count: int = 3


@dataclass(frozen=True, kw_only=True)
class SchedulePreview:
    """The next occurrences as UTC instants; none when the schedule is off."""

    timezone: str
    runs: list[datetime]


class PreviewSchedule(UseCase[PreviewScheduleQuery, SchedulePreview]):
    """Evaluate an expression with the engine the scheduler itself runs.

    A preview that disagreed with the real schedule would be worse than none, so the
    same evaluator answers both. An empty expression means the job is off.
    """

    access: ClassVar[Access] = Requires(SchedulingPermission.READ)

    def __init__(self, evaluator: ScheduleEvaluator, guard: AccessGuard) -> None:
        self._evaluator = evaluator
        self._guard = guard

    async def _handle(
        self, request: PreviewScheduleQuery, actor: Actor
    ) -> SchedulePreview:
        if not 1 <= request.count <= MAX_PREVIEW_RUNS:
            msg = f"Ask for between 1 and {MAX_PREVIEW_RUNS} runs"
            raise ValidationError(msg)
        expression = request.expression.strip()
        runs: list[datetime] = []
        after = utc_instant(request.now)
        while expression and len(runs) < request.count:
            fire = await self._evaluator.next_fire(
                expression, request.timezone, after=after
            )
            if fire is None:
                break
            runs.append(fire)
            after = fire
        return SchedulePreview(timezone=request.timezone, runs=runs)
