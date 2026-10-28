import asyncio
import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from app.entrypoints.api.shared.access_guard import get_access_guard
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
from app.platform.config.backup import BackupSettings
from app.shared_kernel.access_guard import DenyAllAccessGuard
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from pathlib import Path

    from app.modules.backup.domain.backup import BackupSummary


@pytest.fixture
def archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BackupSummary:
    """Store a real archive so command tests exercise integrity and streaming."""
    settings = BackupSettings(path=tmp_path / "backups")
    monkeypatch.setattr(commands, "get_backup_settings", lambda: settings)
    monkeypatch.setattr(commands, "_guard", get_access_guard())
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
    archive: BackupSummary, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command lifecycle preserves bytes and exposes useful JSON output."""
    commands.list_backups()
    assert json.loads(capsys.readouterr().out)[0]["id"] == str(archive.id)
    commands.verify(archive.id)
    assert json.loads(capsys.readouterr().out) == {"findings": []}
    output = tmp_path / "download.tar.gz"
    commands.download(archive.id, output)
    assert output.read_bytes().startswith(b"\x1f\x8b")
    commands.upload(output)
    uploaded = json.loads(capsys.readouterr().out)
    assert uploaded["id"] != str(archive.id)
    commands.delete(archive.id)
    commands.list_backups()
    assert [item["id"] for item in json.loads(capsys.readouterr().out)] == [
        uploaded["id"]
    ]


def test_prune_dry_run_and_refusal(
    archive: BackupSummary, capsys: pytest.CaptureFixture[str]
) -> None:
    """Dry run keeps archives and invalid retention exits clearly."""
    commands.prune(keep_last=1, older_than_days=0, dry_run=True)
    assert str(archive.id) in json.loads(capsys.readouterr().out)["kept"]
    with pytest.raises(SystemExit, match="1"):
        commands.prune(keep_last=-1)
    assert "cannot be negative" in capsys.readouterr().err


def test_create_and_restore_use_composition(
    archive: BackupSummary,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Create and restore forward their options to the composition root."""
    create = AsyncMock(return_value=archive)
    restore = AsyncMock()
    monkeypatch.setattr(commands, "_create", create)
    monkeypatch.setattr(commands, "_restore", restore)
    commands.create(label="scheduled")
    assert json.loads(capsys.readouterr().out)["id"] == str(archive.id)
    create.assert_awaited_once_with("scheduled")
    commands.restore(archive.id, replace=True)
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
    capsys: pytest.CaptureFixture[str],
) -> None:
    """User commands authorise the operator and pass the explicit owner onward."""
    from uuid import uuid7

    owner_id = uuid7()
    output = tmp_path / "user.tar.gz"
    export = AsyncMock(return_value=archive)
    import_operation = AsyncMock()
    monkeypatch.setattr(commands, "_export_user", export)
    monkeypatch.setattr(commands, "_import_user", import_operation)
    commands.export_user(output, user=owner_id)
    export.assert_awaited_once_with(owner_id, output)
    assert json.loads(capsys.readouterr().out)["id"] == str(archive.id)
    commands.import_user(output, user=owner_id)
    import_operation.assert_awaited_once_with(owner_id, output)
    monkeypatch.setattr(commands, "_guard", DenyAllAccessGuard())
    with pytest.raises(SystemExit, match="1"):
        commands.export_user(output, user=owner_id)
    with pytest.raises(SystemExit, match="1"):
        commands.import_user(output, user=owner_id)
    assert export.await_count == import_operation.await_count == 1
