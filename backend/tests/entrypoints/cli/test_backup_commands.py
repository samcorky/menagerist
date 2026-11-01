import asyncio
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
from app.entrypoints.api.shared.settings_reader import get_settings_reader
from app.modules.backup.adapters.cli import backup_app as commands
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_database_snapshot import (
    InMemoryDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.application.create_backup import (
    CreateBackup,
    CreateBackupCommand,
)
from app.modules.settings.domain.setting import SettingScope, StoredSetting
from app.platform.config.backup import BackupSettings
from app.shared_kernel.access_guard import DenyAllAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from pathlib import Path

    from app.modules.backup.domain.backup import BackupSummary
    from app.modules.settings.adapters.persistence.in_memory_setting_value_repository import (  # noqa: E501
        InMemorySettingValueRepository,
    )


@pytest.fixture
def backup_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BackupSettings:
    """Point the commands at a temporary archive directory and the wired services."""
    settings = BackupSettings(path=tmp_path / "backups")
    monkeypatch.setattr(commands, "get_backup_settings", lambda: settings)
    monkeypatch.setattr(commands, "_guard", get_access_guard())
    monkeypatch.setattr(commands, "_settings", get_settings_reader)
    return settings


@pytest.fixture
def archive(backup_settings: BackupSettings) -> BackupSummary:
    """Store a real archive so command tests exercise integrity and streaming."""
    settings = backup_settings
    return asyncio.run(
        CreateBackup(
            LocalDirectoryBackupStore(settings.path),
            InMemoryDatabaseSnapshot("old", {"data/users.ndjson": b"{}\n"}),
            InMemoryMediaFiles(),
            get_access_guard(),
            app_version="test",
        ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
    )


def test_list_verify_download_upload_delete(
    archive: BackupSummary, tmp_path: Path
) -> None:
    """The command lifecycle preserves bytes and returns what it did."""
    listed = commands.list_backups()
    assert listed.title == "Backups"
    assert listed.empty == "No backups yet."
    assert [row["id"] for row in listed.value] == [archive.id]  # type: ignore[attr-defined]
    verified = commands.verify(archive.id)
    assert verified.exit_code == 0
    assert verified.value["message"] == "Backup is intact"  # type: ignore[index]
    assert verified.value["findings"] == []  # type: ignore[index]
    output = tmp_path / "download.tar.gz"
    downloaded = commands.download(archive.id, output)
    assert output.read_bytes().startswith(b"\x1f\x8b")
    assert downloaded["output"] == str(output)
    assert downloaded["size"] == output.stat().st_size
    uploaded = commands.upload(output)
    assert uploaded["id"] != archive.id
    assert commands.delete(archive.id)["message"] == "Backup deleted"
    assert [row["id"] for row in commands.list_backups().value] == [uploaded["id"]]  # type: ignore[attr-defined]


def test_prune_dry_run_and_refusal(
    archive: BackupSummary, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dry run keeps archives and invalid retention exits clearly."""
    report = commands.prune(keep_last=1, older_than_days=0, dry_run=True)
    assert report.value["message"] == "Dry run: nothing was deleted"  # type: ignore[index]
    assert str(archive.id) in report.value["kept"]  # type: ignore[index]
    with pytest.raises(SystemExit, match="1"):
        commands.prune(keep_last=-1)
    assert "cannot be negative" in capsys.readouterr().err


def test_create_and_restore_use_composition(
    archive: BackupSummary,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create and restore forward their options to the composition root."""
    create = AsyncMock(return_value=archive)
    restore = AsyncMock()
    monkeypatch.setattr(commands, "_create", create)
    monkeypatch.setattr(commands, "_restore", restore)
    created = commands.create(label="scheduled")
    assert created["id"] == archive.id
    assert created["message"] == "Backup created and verified"
    create.assert_awaited_once_with("scheduled")
    restored = commands.restore(archive.id, replace=True)
    assert restored["replaced_existing_data"] is True
    assert restore.await_args is not None
    assert restore.await_args.args[1] is True


def test_unwired_authorisation_fails_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An unwired command refuses to create a backup before any DB access."""
    monkeypatch.setattr(commands, "_guard", DenyAllAccessGuard())
    with pytest.raises(SystemExit, match="1"):
        commands.create()
    assert "not wired" in capsys.readouterr().err


def test_user_transfers_require_explicit_owner(
    archive: BackupSummary,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """User commands authorise the operator and pass the explicit owner onward."""
    from uuid import uuid7

    owner_id = uuid7()
    output = tmp_path / "user.tar.gz"
    export = AsyncMock(return_value=archive)
    import_operation = AsyncMock()
    monkeypatch.setattr(commands, "_export_user", export)
    monkeypatch.setattr(commands, "_import_user", import_operation)
    exported = commands.export_user(output, user=owner_id)
    export.assert_awaited_once_with(owner_id, output)
    assert exported["id"] == archive.id
    imported = commands.import_user(output, user=owner_id)
    assert imported["user"] == str(owner_id)
    import_operation.assert_awaited_once_with(owner_id, output)
    monkeypatch.setattr(commands, "_guard", DenyAllAccessGuard())
    with pytest.raises(SystemExit, match="1"):
        commands.export_user(output, user=owner_id)
    with pytest.raises(SystemExit, match="1"):
        commands.import_user(output, user=owner_id)
    assert export.await_count == import_operation.await_count == 1


def _save(store: InMemorySettingValueRepository, key: str, value: int) -> None:
    asyncio.run(
        store.save(
            StoredSetting.create(
                scope=SettingScope.INSTANCE,
                owner_id=None,
                key=key,
                value=value,
                updated_by=None,
            )
        )
    )


def _add_archives(settings: BackupSettings, count: int) -> None:
    for _ in range(count):
        asyncio.run(
            CreateBackup(
                LocalDirectoryBackupStore(settings.path),
                InMemoryDatabaseSnapshot("old", {"data/users.ndjson": b"{}\n"}),
                InMemoryMediaFiles(),
                get_access_guard(),
                app_version="test",
            ).handle(CreateBackupCommand(), SYSTEM_ACTOR)
        )


def test_prune_follows_the_retention_an_administrator_saved(
    archive: BackupSummary,
    backup_settings: BackupSettings,
    settings_store: InMemorySettingValueRepository,
) -> None:
    """Without a saved value seven are kept; with keep_last 2 the oldest goes."""
    del archive
    _add_archives(backup_settings, 2)
    report = commands.prune(dry_run=True).value
    assert (len(report["kept"]), report["deleted"]) == (3, [])  # type: ignore[index]
    _save(settings_store, "backup.keep_last", 2)
    get_settings_reader().invalidate()  # the API does this after a save
    report = commands.prune(dry_run=True).value
    assert (len(report["kept"]), len(report["deleted"])) == (2, 1)  # type: ignore[index]


def test_prune_needs_the_settings_to_be_wired(
    archive: BackupSummary,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A command run outside the composition root refuses rather than guessing."""
    del archive
    monkeypatch.setattr(commands, "_settings", commands._UnwiredSettings)
    with pytest.raises(SystemExit, match="1"):
        commands.prune(dry_run=True)
    assert "not wired" in capsys.readouterr().err
