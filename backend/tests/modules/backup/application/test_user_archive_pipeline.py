from uuid import uuid7

import pytest

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
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor


async def test_personal_download_import_and_temporary_cleanup() -> None:
    """The streamed API pipeline retains exported IDs and assigns the new owner."""
    source, destination = Actor(id=uuid7()), Actor(id=uuid7())
    node_id = uuid7()
    store = InMemoryBackupStore()
    media, guard = InMemoryMediaFiles(), InMemoryAccessGuard()
    snapshot = InMemoryUserDatabaseSnapshot(
        "revision",
        {
            "nodes": [{"id": node_id, "owner_id": source.id, "name": "Imported item"}],
        },
    )
    summary = await ExportUserData(
        store, snapshot, media, guard, app_version="test"
    ).handle(ExportUserDataCommand(), source)
    opened = await OpenUserExport(store, guard).handle(
        OpenUserExportQuery(backup_id=summary.id), source
    )
    assert opened.summary.id == summary.id
    with pytest.raises(BackupNotFoundError):
        await OpenUserExport(store, guard).handle(
            OpenUserExportQuery(backup_id=uuid7()), source
        )
    target = InMemoryUserDatabaseRestorer("revision")
    workspace = InMemoryBackupWorkspace()
    upload_store = InMemoryBackupStore()
    importer = ImportUserArchive(
        upload_store,
        ImportUserData(upload_store, target, media, workspace, guard),
        workspace,
        guard,
    )
    await importer.handle(ImportUserArchiveCommand(stream=opened.chunks), destination)
    row = target.tables["nodes"][0]
    assert str(row["id"]) == str(node_id)
    assert str(row["owner_id"]) == str(destination.id)
    assert await upload_store.list() == []
    with pytest.raises(RestoreTargetNotEmptyError):
        await importer.handle(
            ImportUserArchiveCommand(stream=store.read_bytes(summary.id)), destination
        )
    assert await upload_store.list() == []
