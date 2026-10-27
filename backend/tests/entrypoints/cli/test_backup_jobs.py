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
