"""Calendar evaluator contracts and DST-aware next-fire previews."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_evaluator import (
    InMemoryScheduleEvaluator,
)

if TYPE_CHECKING:
    from app.modules.scheduling.ports.schedule_evaluator import ScheduleEvaluator

NOW = datetime(2026, 10, 26, 3, tzinfo=UTC)
EXPRESSION = "0 3 * * *"


@pytest.fixture(params=["cron", "in_memory"])
def evaluator(request: pytest.FixtureRequest) -> ScheduleEvaluator:
    """Both adapters answer the same absolute-time questions."""
    if request.param == "cron":
        return CronScheduleEvaluator()
    return InMemoryScheduleEvaluator({EXPRESSION: [NOW, NOW + timedelta(days=1)]})


async def test_calendar_interval_boundaries(evaluator: ScheduleEvaluator) -> None:
    """Include the upper boundary; exclude the lower and current preview instants."""
    assert (
        await evaluator.latest_fire(
            EXPRESSION, "UTC", after=NOW - timedelta(hours=1), until=NOW
        )
        == NOW
    )
    assert (
        await evaluator.latest_fire(
            EXPRESSION, "UTC", after=NOW, until=NOW + timedelta(hours=1)
        )
        is None
    )
    assert await evaluator.next_fire(EXPRESSION, "UTC", after=NOW) == NOW + timedelta(
        days=1
    )


async def test_empty_in_memory_calendar() -> None:
    """Fixtures can model a calendar with no matching occurrence."""
    evaluator = InMemoryScheduleEvaluator({EXPRESSION: []})
    assert (
        await evaluator.latest_fire(
            EXPRESSION, "UTC", after=NOW, until=NOW + timedelta(days=1)
        )
        is None
    )
    assert await evaluator.next_fire(EXPRESSION, "UTC", after=NOW) is None


async def test_next_preview_handles_both_dst_transitions() -> None:
    """Calendar previews use the same DST rules as scheduling evaluation."""
    evaluator = CronScheduleEvaluator()
    spring = datetime(2026, 3, 29, 0, tzinfo=UTC)
    assert await evaluator.next_fire(
        "30 1 * * *", "Europe/London", after=spring
    ) == datetime(2026, 3, 29, 1, tzinfo=UTC)
    autumn = datetime(2026, 10, 25, 1, tzinfo=UTC)
    assert await evaluator.next_fire(
        "30 1 * * *", "Europe/London", after=autumn
    ) == datetime(2026, 10, 26, 1, 30, tzinfo=UTC)
