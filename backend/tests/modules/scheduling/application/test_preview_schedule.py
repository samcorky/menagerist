"""Previewing when a schedule would next run."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.application.preview_schedule import (
    MAX_PREVIEW_RUNS,
    PreviewSchedule,
    PreviewScheduleQuery,
)
from app.shared_kernel.actor import Actor
from app.shared_kernel.errors import ForbiddenError, ValidationError

ADMIN = Actor(id=uuid7(), roles=frozenset({"admin"}))
MEMBER = Actor(id=uuid7(), roles=frozenset({"member"}))


def query(
    expression: str, *, now: datetime, zone: str = "UTC", count: int = 3
) -> PreviewScheduleQuery:
    """A preview request."""
    return PreviewScheduleQuery(
        expression=expression, timezone=zone, now=now, count=count
    )


def preview() -> PreviewSchedule:
    """The use case over the real evaluator."""
    return PreviewSchedule(CronScheduleEvaluator(), get_access_guard())


async def test_it_lists_the_next_runs_soonest_first() -> None:
    """Three daily runs follow the instant it counts from, and none is in the past."""
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    result = await preview().handle(query("0 3 * * *", now=now), ADMIN)
    assert result.timezone == "UTC"
    assert result.runs == [
        datetime(2026, 10, 29, 3, tzinfo=UTC),
        datetime(2026, 10, 30, 3, tzinfo=UTC),
        datetime(2026, 10, 31, 3, tzinfo=UTC),
    ]


async def test_the_runs_follow_the_clocks_going_back() -> None:
    """03:00 in London is 02:00 UTC in summer and 03:00 UTC once the clocks change."""
    now = datetime(2026, 10, 23, 12, tzinfo=UTC)
    result = await preview().handle(
        query("0 3 * * *", now=now, zone="Europe/London"), ADMIN
    )
    assert result.runs[:2] == [
        datetime(2026, 10, 24, 2, tzinfo=UTC),
        datetime(2026, 10, 25, 3, tzinfo=UTC),
    ]


async def test_an_off_schedule_has_no_runs() -> None:
    """An empty expression means the job is off."""
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    for blank in ("", "   "):
        result = await preview().handle(query(blank, now=now), ADMIN)
        assert result.runs == []
        assert result.timezone == "UTC"


async def test_a_schedule_the_server_would_refuse_is_a_validation_error() -> None:
    """The same evaluator that runs the job refuses what it cannot run."""
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    for bad in ("61 * * * *", "0 3 * *", "0 0 3 * * *", "@daily", "0 3 ? * *"):
        with pytest.raises(ValidationError):
            await preview().handle(query(bad, now=now), ADMIN)


@pytest.mark.parametrize("count", [0, MAX_PREVIEW_RUNS + 1])
async def test_the_number_of_runs_is_bounded(count: int) -> None:
    """Asking for none, or for a flood, is refused."""
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    with pytest.raises(ValidationError, match="between 1 and"):
        await preview().handle(query("0 3 * * *", now=now, count=count), ADMIN)


async def test_it_stops_when_a_schedule_has_no_more_runs() -> None:
    """An evaluator with nothing further ends the list rather than looping."""

    class Exhausted:
        async def next_fire(
            self, expression: str, timezone: str, *, after: datetime
        ) -> datetime | None:
            return None

        async def latest_fire(
            self, expression: str, timezone: str, *, after: datetime, until: datetime
        ) -> datetime | None:
            return None

    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    result = await PreviewSchedule(Exhausted(), get_access_guard()).handle(
        query("0 3 * * *", now=now), ADMIN
    )
    assert result.runs == []


async def test_only_administrators_may_preview() -> None:
    """Scheduled tasks are an administrator's concern."""
    now = datetime(2026, 10, 28, 12, tzinfo=UTC)
    with pytest.raises(ForbiddenError):
        await preview().handle(query("0 3 * * *", now=now), MEMBER)
