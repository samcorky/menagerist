from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from uuid import uuid7

from app.entrypoints.api.shared.authorisation import RoleAuthorisationAdapter
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.adapters.storage.local_backup_store import (
    LocalDirectoryBackupStore,
)
from app.modules.backup.application.prune_backups import (
    PruneBackups,
    PruneBackupsCommand,
)
from app.modules.backup.domain.backup import BackupManifest, BackupScope
from app.shared_kernel.actor import SYSTEM_ACTOR

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from app.modules.backup.domain.backup import BackupSummary
    from app.modules.backup.ports.backup_store import BackupStore


async def _export(store: BackupStore, age: timedelta) -> BackupSummary:
    owner = uuid7()
    writer = await store.begin(uuid7())
    stored = await writer.finish(
        BackupManifest(
            app_version="test",
            alembic_revision="rev",
            label="user-export",
            scope=BackupScope.USER,
            owner_id=owner,
            created_by=owner,
            created_at=datetime.now(UTC) - age,
        )
    )
    return stored.summary


async def test_global_prune_expires_inactive_users_exports() -> None:
    """Housekeeping reaps exports without waiting for another user request."""
    root, user = InMemoryBackupStore(), InMemoryBackupStore()
    owner = uuid7()
    root.user_stores[owner] = user
    expired = await _export(user, timedelta(hours=3))
    recent = await _export(user, timedelta(minutes=30))
    prune = PruneBackups(root, RoleAuthorisationAdapter(), user_export_ttl_hours=2)
    report = await prune.handle(PruneBackupsCommand(dry_run=True), SYSTEM_ACTOR)
    expected = [f"users/{owner}/instance/{expired.id}.tar.gz"]
    assert report.user_exports_removed == expected
    assert len(await user.list()) == 2
    report = await prune.handle(PruneBackupsCommand(), SYSTEM_ACTOR)
    assert report.user_exports_removed == expected
    assert await user.list() == [recent]


async def test_local_expiry_ignores_unrecognised_and_unreadable_namespaces(
    tmp_path: Path,
) -> None:
    """Only canonical user directories and readable committed exports are pruned."""
    store = LocalDirectoryBackupStore(tmp_path)
    owner = uuid7()
    user = LocalDirectoryBackupStore(tmp_path / "users" / str(owner))
    expired = await _export(user, timedelta(days=2))
    recent = await _export(user, timedelta(minutes=5))
    invalid = LocalDirectoryBackupStore(tmp_path / "users" / "not-a-user")
    ignored = await _export(invalid, timedelta(days=2))
    (tmp_path / "users" / str(owner) / "instance" / f"{uuid7()}.json").write_text(
        "invalid"
    )
    before = datetime.now(UTC) - timedelta(days=1)
    expected = [f"users/{owner}/instance/{expired.id}.tar.gz"]
    assert await store.cleanup_user_exports(before=before, dry_run=True) == expected
    assert len(await user.list()) == 2
    assert await store.cleanup_user_exports(before=before, dry_run=False) == expected
    assert await user.list() == [recent]
    assert await invalid.list() == [ignored]


async def test_user_retention_does_not_follow_directory_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A linked owner namespace cannot redirect housekeeping outside its root."""
    from pathlib import Path

    owner = uuid7()
    namespace = tmp_path / "users" / str(owner)
    user = LocalDirectoryBackupStore(namespace)
    expired = await _export(user, timedelta(days=2))
    original = Path.is_symlink
    monkeypatch.setattr(
        Path, "is_symlink", lambda path: path == namespace or original(path)
    )
    assert (
        await LocalDirectoryBackupStore(tmp_path).cleanup_user_exports(
            before=datetime.now(UTC), dry_run=False
        )
        == []
    )
    assert await user.list() == [expired]
