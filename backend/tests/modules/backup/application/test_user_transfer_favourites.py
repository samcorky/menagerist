"""A personal archive carries only the exporting person's own favourites."""

from uuid import UUID, uuid7

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
from app.modules.backup.application.import_user_data import (
    ImportUserData,
    ImportUserDataCommand,
)
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor


async def _export(
    actor: Actor, tables: dict[str, list[dict[str, object]]]
) -> tuple[InMemoryBackupStore, UUID]:
    store = InMemoryBackupStore()
    summary = await ExportUserData(
        store,
        InMemoryUserDatabaseSnapshot("rev", tables),
        InMemoryMediaFiles(),
        InMemoryAccessGuard(),
        app_version="test",
    ).handle(ExportUserDataCommand(), actor)
    return store, summary.id


async def test_export_and_import_carry_only_the_exporters_favourites() -> None:
    """Someone else's star on the item, and stars on others' items, stay behind."""
    me, other = Actor(id=uuid7()), Actor(id=uuid7())
    mine, mine_too, theirs = uuid7(), uuid7(), uuid7()
    when = "2026-11-04T10:00:00+00:00"
    tables: dict[str, list[dict[str, object]]] = {
        "nodes": [
            {"id": mine, "owner_id": me.id, "name": "Mine", "type": None},
            {"id": mine_too, "owner_id": me.id, "name": "Plain", "type": None},
            {"id": theirs, "owner_id": other.id, "name": "Theirs", "type": None},
        ],
        "node_favourites": [
            {"user_id": me.id, "node_id": mine, "created_at": when},
            {"user_id": other.id, "node_id": mine, "created_at": when},
            {"user_id": other.id, "node_id": theirs, "created_at": when},
        ],
    }
    store, backup_id = await _export(me, tables)
    destination = Actor(id=uuid7())
    restorer = InMemoryUserDatabaseRestorer("rev")

    await ImportUserData(
        store,
        restorer,
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        InMemoryAccessGuard(),
    ).handle(ImportUserDataCommand(backup_id=backup_id), destination)

    favourites = restorer.tables["node_favourites"]
    assert [(str(row["user_id"]), str(row["node_id"])) for row in favourites] == [
        (str(destination.id), str(mine))
    ]


async def test_an_item_without_favourites_exports_none() -> None:
    """No rows for the person means an empty table member, not an error."""
    me = Actor(id=uuid7())
    tables: dict[str, list[dict[str, object]]] = {
        "nodes": [{"id": uuid7(), "owner_id": me.id, "name": "Mine", "type": None}],
    }
    store, backup_id = await _export(me, tables)
    restorer = InMemoryUserDatabaseRestorer("rev")

    await ImportUserData(
        store,
        restorer,
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        InMemoryAccessGuard(),
    ).handle(ImportUserDataCommand(backup_id=backup_id), Actor(id=uuid7()))

    assert restorer.tables["node_favourites"] == []
