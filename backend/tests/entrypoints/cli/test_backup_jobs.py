"""Scheduled backups reuse the backup use cases through the composition root."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from app.entrypoints.cli import backup_jobs
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane, MissedRun, Overlap

if TYPE_CHECKING:
    from pathlib import Path

    from app.modules.scheduling.adapters.cli.catalogue import JobBinding


def _bindings(calls: list[str]) -> dict[str, JobBinding]:
    def recorder(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda actor: calls.append(name))

    return {
        binding.definition.job_key: binding
        for binding in backup_jobs.backup_job_bindings(
            create=recorder("create"),
            prune=recorder("prune"),
            prune_exports=recorder("prune_exports"),
        )
    }


def test_job_policies() -> None:
    """Backups are heavy and catch up once; export expiry is light."""
    jobs = _bindings([])
    create = jobs["backup.create"].definition
    assert create.lane is Lane.HEAVY
    assert create.overlap is Overlap.COALESCE
    assert create.missed_run is MissedRun.RUN_ONCE
    assert create.schedule_key == "backup.schedule"
    exports = jobs["backup.prune_exports"].definition
    assert exports.lane is Lane.DEFAULT
    assert exports.schedule_key == "backup.prune_exports_schedule"
    assert set(jobs) == {"backup.create", "backup.prune_exports"}


async def test_retention_prunes_only_after_a_backup_completes() -> None:
    """Retention follows a successful backup; a failed backup prunes nothing."""
    calls: list[str] = []
    jobs = _bindings(calls)
    await jobs["backup.create"].handler(SYSTEM_ACTOR)
    assert calls == ["create", "prune"]

    failing = AsyncMock(side_effect=RuntimeError("disk full"))
    prune = AsyncMock()
    binding = next(
        item
        for item in backup_jobs.backup_job_bindings(
            create=failing, prune=prune, prune_exports=AsyncMock()
        )
        if item.definition.job_key == "backup.create"
    )
    with pytest.raises(RuntimeError):
        await binding.handler(SYSTEM_ACTOR)
    prune.assert_not_awaited()


async def test_export_expiry_never_prunes_backups() -> None:
    """The hourly job only expires exports."""
    calls: list[str] = []
    await _bindings(calls)["backup.prune_exports"].handler(SYSTEM_ACTOR)
    assert calls == ["prune_exports"]


def test_schedule_values_come_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployment schedules feed the schedule source; empty keeps a job off."""
    monkeypatch.setattr(
        backup_jobs,
        "get_backup_settings",
        Mock(return_value=Mock(schedule="", prune_exports_schedule="5 * * * *")),
    )
    assert backup_jobs.backup_schedules() == {
        "backup.schedule": "",
        "backup.prune_exports_schedule": "5 * * * *",
    }


async def test_missing_media_directory_fails_loudly(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A worker without the API's media volume must not report an empty backup."""
    monkeypatch.setattr(
        backup_jobs,
        "get_media_settings",
        Mock(return_value=Mock(media_storage_path=tmp_path / "absent")),
    )
    with pytest.raises(FileNotFoundError, match="media"):
        await backup_jobs.create_scheduled_backup(SYSTEM_ACTOR)


@pytest.mark.parametrize(
    ("value", "runs"), [("", 0), ("0 3 * * *", 1)], ids=["empty-is-off", "control"]
)
async def test_empty_environment_value_stops_the_job_ever_being_enqueued(
    monkeypatch: pytest.MonkeyPatch, value: str, runs: int
) -> None:
    """From the environment to a real tick: empty enqueues nothing, a cron does."""
    from datetime import UTC, datetime, timedelta

    from app.entrypoints.api.shared.access_guard import get_access_guard
    from app.entrypoints.cli.scheduling import build_schedule_source
    from app.modules.scheduling.adapters.cli.catalogue import JobCatalogue
    from app.modules.scheduling.adapters.persistence.in_memory_store import (
        InMemorySchedulingStore,
    )
    from app.modules.scheduling.adapters.persistence.unit_of_work import (
        create_in_memory_scheduling_uow,
    )
    from app.modules.scheduling.adapters.platform.cron_evaluator import (
        CronScheduleEvaluator,
    )
    from app.modules.scheduling.application.tick_schedules import (
        TickSchedules,
        TickSchedulesCommand,
    )
    from app.platform.config.backup import get_backup_settings

    monkeypatch.setenv("MENAGERIST_BACKUP_SCHEDULE", value)
    get_backup_settings.cache_clear()
    try:
        source = build_schedule_source()
        assert await source.schedule_for("backup.schedule") == (value or None)
        store = InMemorySchedulingStore()
        catalogue = JobCatalogue(_bindings([]).values())
        start = datetime(2026, 10, 27, 12, tzinfo=UTC)
        for now in (start, start + timedelta(days=1)):
            await TickSchedules(
                create_in_memory_scheduling_uow(store),
                get_access_guard(),
                catalogue.registry,
                source,
                CronScheduleEvaluator(),
            ).handle(TickSchedulesCommand(now=now, timezone="UTC"), SYSTEM_ACTOR)
    finally:
        get_backup_settings.cache_clear()
    assert [run.job_key for run in store.runs.values()].count("backup.create") == runs
