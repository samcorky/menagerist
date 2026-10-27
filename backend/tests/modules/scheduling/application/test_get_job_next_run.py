"""A job's next occurrence is resolved from its effective schedule."""

from datetime import UTC, datetime
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.modules.scheduling.adapters.platform.cron_evaluator import (
    CronScheduleEvaluator,
)
from app.modules.scheduling.adapters.platform.in_memory_schedule_source import (
    InMemoryScheduleSource,
)
from app.modules.scheduling.application.get_job_next_run import (
    GetJobNextRun,
    GetJobNextRunQuery,
)
from app.modules.scheduling.domain.errors import UnknownJobError
from app.modules.scheduling.domain.registry import JobRegistry
from app.shared_kernel.actor import SYSTEM_ACTOR, Actor
from app.shared_kernel.errors import ForbiddenError
from app.shared_kernel.jobs import JobDefinition

NOW = datetime(2026, 10, 27, 12, tzinfo=UTC)
REGISTRY = JobRegistry(
    [
        JobDefinition(job_key="scheduled", schedule_key="scheduled.cron"),
        JobDefinition(job_key="disabled", schedule_key="disabled.cron"),
        JobDefinition(job_key="manual"),
    ]
)


def _query(job_key: str, timezone: str = "UTC") -> GetJobNextRunQuery:
    return GetJobNextRunQuery(job_key=job_key, now=NOW, timezone=timezone)


def _use_case() -> GetJobNextRun:
    return GetJobNextRun(
        REGISTRY,
        InMemoryScheduleSource({"scheduled.cron": "0 3 * * *", "disabled.cron": ""}),
        CronScheduleEvaluator(),
        get_access_guard(),
    )


async def test_scheduled_job_reports_its_next_fire_in_the_instance_timezone() -> None:
    """The occurrence is evaluated in the supplied zone and returned as UTC."""
    assert await _use_case().handle(_query("scheduled"), SYSTEM_ACTOR) == datetime(
        2026, 10, 28, 3, tzinfo=UTC
    )
    assert await _use_case().handle(
        _query("scheduled", "Europe/London"), SYSTEM_ACTOR
    ) == datetime(2026, 10, 28, 3, tzinfo=UTC)
    assert await _use_case().handle(
        _query("scheduled", "Asia/Tokyo"), SYSTEM_ACTOR
    ) == datetime(2026, 10, 27, 18, tzinfo=UTC)


@pytest.mark.parametrize("job_key", ["disabled", "manual"])
async def test_switched_off_or_unscheduled_jobs_have_no_next_run(job_key: str) -> None:
    """An empty schedule and a run-now-only job both report nothing."""
    assert await _use_case().handle(_query(job_key), SYSTEM_ACTOR) is None


async def test_unknown_job_is_rejected() -> None:
    """Only registered jobs can be asked about."""
    with pytest.raises(UnknownJobError):
        await _use_case().handle(_query("missing"), SYSTEM_ACTOR)


async def test_only_the_system_actor_may_ask() -> None:
    """The worker boundary owns this query."""
    with pytest.raises(ForbiddenError):
        await _use_case().handle(_query("scheduled"), Actor(id=uuid7()))
