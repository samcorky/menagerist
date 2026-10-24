from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid7

import pytest

from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.application.delete_user_export import (
    DeleteUserExport,
    DeleteUserExportCommand,
)
from app.modules.backup.application.export_user_data import (
    ExportUserData,
    ExportUserDataCommand,
)
from app.modules.backup.application.list_user_exports import (
    ListUserExports,
    ListUserExportsQuery,
)
from app.modules.backup.domain.errors import BackupNotFoundError
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor

TTL_HOURS = 24


async def _export(store: InMemoryBackupStore, actor: Actor) -> UUID:
    created = await ExportUserData(
        store,
        InMemoryUserDatabaseSnapshot("rev", {}),
        InMemoryMediaFiles(),
        InMemoryAccessGuard(),
        app_version="test",
    ).handle(ExportUserDataCommand(), actor)
    return created.id


def _age(store: InMemoryBackupStore, backup_id: UUID, age: timedelta) -> None:
    store.summaries[backup_id] = replace(
        store.summaries[backup_id], created_at=datetime.now(UTC) - age
    )


def _lister(store: InMemoryBackupStore) -> ListUserExports:
    return ListUserExports(store, InMemoryAccessGuard(), ttl_hours=TTL_HOURS)


def _deleter(store: InMemoryBackupStore) -> DeleteUserExport:
    return DeleteUserExport(store, InMemoryAccessGuard(), ttl_hours=TTL_HOURS)


async def test_lists_newest_first_with_expiry() -> None:
    """Each export reports when it stops being available."""
    store, actor = InMemoryBackupStore(), Actor(id=uuid7())
    older, newer = await _export(store, actor), await _export(store, actor)
    _age(store, older, timedelta(hours=3))

    listed = await _lister(store).handle(ListUserExportsQuery(), actor)

    assert [item.summary.id for item in listed] == [newer, older]
    for item in listed:
        assert item.expires_at == item.summary.created_at + timedelta(hours=TTL_HOURS)


async def test_lists_nothing_when_there_are_no_exports() -> None:
    """A caller with no exports gets an empty list."""
    assert (
        await _lister(InMemoryBackupStore()).handle(
            ListUserExportsQuery(), Actor(id=uuid7())
        )
        == []
    )


async def test_list_is_scoped_to_the_callers_own_store() -> None:
    """Another account's namespace is a different store and never appears."""
    mine, theirs = InMemoryBackupStore(), InMemoryBackupStore()
    alice, bob = Actor(id=uuid7()), Actor(id=uuid7())
    own = await _export(mine, alice)
    await _export(theirs, bob)

    listed = await _lister(mine).handle(ListUserExportsQuery(), alice)

    assert [item.summary.id for item in listed] == [own]


async def test_expiry_boundary_and_lazy_removal() -> None:
    """Exports older than the retention vanish and are removed from storage."""
    store, actor = InMemoryBackupStore(), Actor(id=uuid7())
    fresh, stale = await _export(store, actor), await _export(store, actor)
    _age(store, fresh, timedelta(hours=TTL_HOURS) - timedelta(minutes=1))
    _age(store, stale, timedelta(hours=TTL_HOURS) + timedelta(minutes=1))

    listed = await _lister(store).handle(ListUserExportsQuery(), actor)

    assert [item.summary.id for item in listed] == [fresh]
    assert stale not in store.archives


async def test_delete_removes_own_export() -> None:
    """Deleting removes the archive and leaves the others."""
    store, actor = InMemoryBackupStore(), Actor(id=uuid7())
    gone, kept = await _export(store, actor), await _export(store, actor)

    await _deleter(store).handle(DeleteUserExportCommand(backup_id=gone), actor)

    assert gone not in store.archives
    assert kept in store.archives


async def test_delete_of_another_accounts_export_is_not_found() -> None:
    """The id exists only in the other account's namespace."""
    mine, theirs = InMemoryBackupStore(), InMemoryBackupStore()
    alice, bob = Actor(id=uuid7()), Actor(id=uuid7())
    other = await _export(theirs, bob)

    with pytest.raises(BackupNotFoundError):
        await _deleter(mine).handle(DeleteUserExportCommand(backup_id=other), alice)

    assert other in theirs.archives


async def test_delete_of_unknown_or_expired_export_is_not_found() -> None:
    """An unknown id and an expired export are both missing."""
    store, actor = InMemoryBackupStore(), Actor(id=uuid7())
    expired = await _export(store, actor)
    _age(store, expired, timedelta(hours=TTL_HOURS, minutes=1))

    for backup_id in (uuid7(), expired):
        with pytest.raises(BackupNotFoundError):
            await _deleter(store).handle(
                DeleteUserExportCommand(backup_id=backup_id), actor
            )
