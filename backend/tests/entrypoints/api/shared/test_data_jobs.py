"""The scheduled purge of long-deleted content."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.entrypoints.api.shared import data_jobs
from app.entrypoints.api.shared.purge_deleted import (
    PurgeDeletedContentCommand,
    PurgeDeletedContentResult,
)
from app.platform.config.retention import RetentionSettings
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    import pytest

    from app.shared_kernel.actor import Actor


class _Purge:
    """Records what it is asked to purge."""

    def __init__(self) -> None:
        self.commands: list[PurgeDeletedContentCommand] = []
        self.actors: list[Actor] = []

    async def handle(
        self, command: PurgeDeletedContentCommand, actor: Actor
    ) -> PurgeDeletedContentResult:
        await asyncio.sleep(0)
        self.commands.append(command)
        self.actors.append(actor)
        return PurgeDeletedContentResult(items=0, connections=0, collections=0)


def test_it_contributes_one_titled_job_that_cannot_be_run_by_hand() -> None:
    """A permanent deletion runs only when an administrator has scheduled it."""
    [binding] = data_jobs.data_job_contribution().bindings()
    job = binding.definition
    assert job.job_key == "data.purge_deleted"
    assert job.schedule_key == "retention.purge_schedule"
    assert job.run_now_allowed is False
    assert job.title.strip()
    assert "Recently deleted" in job.description
    assert binding.handler is data_jobs.purge_deleted_content


async def test_it_purges_what_was_deleted_before_the_retention_period(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cutoff is the configured retention, and nothing is only counted."""
    purge = _Purge()
    monkeypatch.setattr(data_jobs, "build_purge_deleted_content", lambda: purge)
    monkeypatch.setattr(
        data_jobs, "get_retention_settings", lambda: RetentionSettings(deleted_days=14)
    )

    before = datetime.now(UTC)
    await data_jobs.purge_deleted_content(SYSTEM_ACTOR)
    after = datetime.now(UTC)

    [command] = purge.commands
    assert purge.actors == [SYSTEM_ACTOR]
    assert command.dry_run is False
    assert before - timedelta(days=14) <= command.older_than
    assert command.older_than <= after - timedelta(days=14)


def test_the_job_is_off_unless_a_schedule_is_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Out of the box nothing is permanently deleted on a timer."""
    monkeypatch.setattr(
        data_jobs, "get_retention_settings", lambda: RetentionSettings()
    )
    assert data_jobs.data_job_contribution().schedules() == {
        "retention.purge_schedule": ""
    }
    assert RetentionSettings(purge_schedule="30 4 * * *").purge_schedule == "30 4 * * *"
