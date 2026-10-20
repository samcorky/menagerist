from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid7

import pytest

from app.entrypoints.api.shared.access_policy import OwnerAccessPolicy
from app.modules.backup.adapters.media.in_memory_media_files import InMemoryMediaFiles
from app.modules.backup.adapters.persistence.in_memory_user_database_restorer import (
    InMemoryUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_store import (
    InMemoryBackupStore,
)
from app.modules.backup.adapters.storage.in_memory_backup_workspace import (
    InMemoryBackupWorkspace,
)
from app.modules.backup.application.export_user_data import (
    ExportUserData,
    ExportUserDataCommand,
)
from app.modules.backup.application.import_user_archive import (
    ImportUserArchive,
    ImportUserArchiveCommand,
)
from app.modules.backup.application.import_user_data import ImportUserData
from app.modules.backup.application.open_user_export import (
    OpenUserExport,
    OpenUserExportQuery,
)
from app.modules.backup.domain.errors import (
    BackupNotFoundError,
    RestoreTargetNotEmptyError,
)
from app.shared_kernel.actor import Actor


async def test_personal_download_prunes_expired_archives_and_scans_summaries() -> None:
    """Downloads remove expired files and find the requested archive among others."""
    store, actor, policy = InMemoryBackupStore(), Actor(id=uuid7()), OwnerAccessPolicy()
    creator = ExportUserData(
        store,
        InMemoryUserDatabaseSnapshot("rev", {}),
        InMemoryMediaFiles(),
        policy,
        app_version="test",
    )
    first = await creator.handle(ExportUserDataCommand(), actor)
    second = await creator.handle(ExportUserDataCommand(), actor)
    opened = await OpenUserExport(store, policy).handle(
        OpenUserExportQuery(backup_id=second.id), actor
    )
    assert (
        b"".join([chunk async for chunk in opened.chunks]) == store.archives[second.id]
    )
    store.summaries[first.id] = replace(
        first, created_at=datetime.now(UTC) - timedelta(days=2)
    )
    with pytest.raises(BackupNotFoundError):
        await OpenUserExport(store, policy).handle(
            OpenUserExportQuery(backup_id=first.id), actor
        )
    assert first.id not in store.archives


@pytest.mark.parametrize("already_populated", [False, True])
async def test_personal_upload_is_deleted_after_import_attempt(
    already_populated: bool,
) -> None:
    """Successful and refused imports both remove the transient committed upload."""
    source, destination = InMemoryBackupStore(), InMemoryBackupStore()
    owner, actor, policy = Actor(id=uuid7()), Actor(id=uuid7()), OwnerAccessPolicy()
    exported = await ExportUserData(
        source,
        InMemoryUserDatabaseSnapshot("rev", {}),
        InMemoryMediaFiles(),
        policy,
        app_version="test",
    ).handle(ExportUserDataCommand(), owner)
    workspace, media = InMemoryBackupWorkspace(), InMemoryMediaFiles()
    target = InMemoryUserDatabaseRestorer(
        "rev",
        {"nodes": [{"id": uuid7(), "owner_id": actor.id}]} if already_populated else {},
    )
    importer = ImportUserData(destination, target, media, workspace, policy)
    use_case = ImportUserArchive(destination, importer, workspace, policy)
    command = ImportUserArchiveCommand(stream=source.read_bytes(exported.id))
    if already_populated:
        with pytest.raises(RestoreTargetNotEmptyError):
            await use_case.handle(command, actor)
    else:
        await use_case.handle(command, actor)
    assert await destination.list() == []
    assert not workspace.files
