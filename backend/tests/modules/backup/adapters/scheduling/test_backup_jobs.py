"""Scheduled backups reuse the backup use cases through the composition root."""

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest

from app.modules.backup.adapters.scheduling import jobs as backup_jobs
from app.modules.settings.domain.setting import SettingScope, StoredSetting
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.jobs import Lane, MissedRun, Overlap
from app.shared_kernel.progress import RecordingProgress

if TYPE_CHECKING:
    from pathlib import Path

    from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
        InMemorySettingValueRepository,
    )
    from app.shared_kernel.jobs import JobBinding


def _bindings() -> dict[str, JobBinding]:
    return {
        binding.definition.job_key: binding
        for binding in backup_jobs.backup_job_contribution().bindings()
    }


def _steps(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[str],
    *,
    create: AsyncMock | None = None,
) -> None:
    """Replace the backup and retention steps with recorders."""

    def recorder(name: str) -> AsyncMock:
        return AsyncMock(side_effect=lambda *_arguments: calls.append(name))

    monkeypatch.setattr(
        backup_jobs, "create_scheduled_backup", create or recorder("create")
    )
    monkeypatch.setattr(backup_jobs, "prune_scheduled_backups", recorder("prune"))


async def test_the_scheduled_backup_is_given_the_runs_reporter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The job hands its reporter on, so the run row can show the backup's phases."""
    create = AsyncMock()
    _steps(monkeypatch, [], create=create)
    progress = RecordingProgress()
    await backup_jobs.create_then_prune_backups(SYSTEM_ACTOR, progress)
    create.assert_awaited_once_with(SYSTEM_ACTOR, progress)


async def test_the_backup_composition_receives_the_reporter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`create_scheduled_backup` forwards the reporter to the composed use case."""
    from app.entrypoints.api.shared import backup_operations

    created = AsyncMock()
    monkeypatch.setattr(backup_operations, "create_backup", created)
    media = tmp_path / "media"
    media.mkdir()
    monkeypatch.setattr(
        backup_jobs,
        "get_media_settings",
        lambda: Mock(storage_path=media),
    )
    progress = RecordingProgress()
    await backup_jobs.create_scheduled_backup(SYSTEM_ACTOR, progress)
    created.assert_awaited_once_with(
        label="scheduled", actor=SYSTEM_ACTOR, progress=progress
    )


def test_job_policies() -> None:
    """Backups are heavy and catch up once; export expiry is light."""
    jobs = _bindings()
    create = jobs["backup.create"].definition
    assert create.lane is Lane.HEAVY
    assert create.overlap is Overlap.COALESCE
    assert create.missed_run is MissedRun.RUN_ONCE
    assert create.schedule_key == "backup.schedule"
    exports = jobs["backup.prune_exports"].definition
    assert exports.lane is Lane.DEFAULT
    assert exports.schedule_key == "backup.prune_exports_schedule"
    assert set(jobs) == {"backup.create", "backup.prune_exports"}


async def test_retention_prunes_only_after_a_backup_completes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retention follows a successful backup; a failed backup prunes nothing."""
    calls: list[str] = []
    _steps(monkeypatch, calls)
    await backup_jobs.create_then_prune_backups(SYSTEM_ACTOR)
    assert calls == ["create", "prune"]

    calls.clear()
    _steps(monkeypatch, calls, create=AsyncMock(side_effect=RuntimeError("disk full")))
    with pytest.raises(RuntimeError):
        await backup_jobs.create_then_prune_backups(SYSTEM_ACTOR)
    assert calls == []


def test_export_expiry_is_its_own_job() -> None:
    """The hourly job is the export step alone, never the backup-and-prune job."""
    jobs = _bindings()
    assert jobs["backup.prune_exports"].handler is backup_jobs.prune_expired_exports
    assert jobs["backup.create"].handler is backup_jobs.create_then_prune_backups


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
        Mock(return_value=Mock(storage_path=tmp_path / "absent")),
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
    from app.entrypoints.api.shared.job_catalogue import build_schedule_source
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
        catalogue = JobCatalogue(_bindings().values())
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


async def _save(store: InMemorySettingValueRepository, key: str, value: int) -> None:
    await store.save(
        StoredSetting.create(
            scope=SettingScope.INSTANCE,
            owner_id=None,
            key=key,
            value=value,
            updated_by=None,
        )
    )


class _SpyPrune:
    """Stands in for a prune use case and records how it was built."""

    built: dict[str, int]

    def __init__(self, store: object, guard: object, **options: int) -> None:
        type(self).built = options

    async def handle(self, request: object, actor: object) -> None:
        return None


@pytest.mark.parametrize(
    ("saved", "keep_last", "ttl"),
    [({}, 7, 24), ({"keep_last": 4, "user_export_ttl_hours": 48}, 4, 48)],
    ids=["defaults", "saved-by-an-administrator"],
)
async def test_scheduled_retention_reads_the_current_settings(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    settings_store: InMemorySettingValueRepository,
    saved: dict[str, int],
    keep_last: int,
    ttl: int,
) -> None:
    """The worker takes retention from settings, so an edit applies to its next run."""
    from app.modules.backup.application import prune_backups, prune_user_exports

    for field, value in saved.items():
        await _save(settings_store, f"backup.{field}", value)
    monkeypatch.setattr(
        backup_jobs,
        "get_backup_settings",
        Mock(return_value=Mock(path=tmp_path, pre_migration_keep=3)),
    )
    monkeypatch.setattr(prune_backups, "PruneBackups", _SpyPrune)
    await backup_jobs.prune_scheduled_backups(SYSTEM_ACTOR)
    assert _SpyPrune.built == {
        "keep_last": keep_last,
        "pre_migration_keep": 3,
        "user_export_ttl_hours": ttl,
    }

    monkeypatch.setattr(prune_user_exports, "PruneUserExports", _SpyPrune)
    await backup_jobs.prune_expired_exports(SYSTEM_ACTOR)
    assert _SpyPrune.built == {"user_export_ttl_hours": ttl}
