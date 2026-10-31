"""The scheduler contributes its own housekeeping job like any other module."""

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

from app.modules.scheduling.adapters.scheduling import jobs as scheduling_jobs
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane, Overlap

if TYPE_CHECKING:
    import pytest


def test_it_contributes_the_prune_job_on_a_default_schedule() -> None:
    """Task history is tidied by a titled job that does not wait for setup."""
    contribution = scheduling_jobs.scheduling_job_contribution()
    [binding] = contribution.bindings()
    definition = binding.definition
    assert definition.job_key == "scheduling.prune_runs"
    assert definition.lane is Lane.DEFAULT
    assert definition.overlap is Overlap.COALESCE
    assert not definition.needs_setup_complete
    assert definition.title.strip()
    assert definition.description.strip()
    assert binding.handler is scheduling_jobs.prune_job_runs
    assert contribution.schedules() == {"scheduling.prune_schedule": "0 4 * * *"}


async def test_the_job_applies_the_current_quota_and_a_week_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each run reads the quota again and forgets workers silent for a week."""
    handle = AsyncMock(return_value=0)
    monkeypatch.setattr(scheduling_jobs, "create_scheduling_uow", Mock())
    monkeypatch.setattr(scheduling_jobs, "get_session_factory", Mock())
    monkeypatch.setattr(
        scheduling_jobs, "PruneJobRuns", Mock(return_value=Mock(handle=handle))
    )
    reader = Mock(get=AsyncMock(return_value=30))
    monkeypatch.setattr(
        "app.entrypoints.api.shared.settings_reader.get_settings_reader",
        Mock(return_value=reader),
    )

    start = datetime.now(UTC)
    await scheduling_jobs.prune_job_runs(SYSTEM_ACTOR)
    end = datetime.now(UTC)

    assert handle.await_args is not None
    [command, actor] = handle.await_args.args
    assert actor is SYSTEM_ACTOR
    assert command.keep_per_job == 30
    cutoff = command.worker_heartbeats_before
    assert start - timedelta(days=7) <= cutoff <= end - timedelta(days=7)
