"""Source links travel with a personal export and import."""

from typing import TYPE_CHECKING
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

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.shared_kernel.content_filter import ContentFilter

LINK_TABLE = "data/source_links.ndjson"


class _SnapshotWithoutLinks(InMemoryUserDatabaseSnapshot):
    """A snapshot as written before source links existed: no links member."""

    def export(self, *, scope: ContentFilter) -> AsyncGenerator[ArchiveMember]:
        inner = super().export(scope=scope)

        async def members() -> AsyncGenerator[ArchiveMember]:
            async for member in inner:
                if member.name != LINK_TABLE:
                    yield member

        return members()


def _tables(
    mine: Actor, other: Actor, item_id: UUID, other_item: UUID
) -> dict[str, list[dict[str, object]]]:
    return {
        "nodes": [
            {"id": item_id, "owner_id": mine.id, "name": "Alien", "type": None},
            {"id": other_item, "owner_id": other.id, "name": "Secret", "type": None},
        ],
        "source_links": [
            {
                "id": uuid7(),
                "owner_id": mine.id,
                "source": "lddb",
                "kind": "item",
                "key": "k1",
                "entity_id": item_id,
                "fields": {"name": "h1"},
            },
            {
                "id": uuid7(),
                "owner_id": other.id,
                "source": "lddb",
                "kind": "item",
                "key": "k-private",
                "entity_id": other_item,
                "fields": {"name": "h2"},
            },
        ],
    }


async def _export(
    snapshot: InMemoryUserDatabaseSnapshot, actor: Actor
) -> tuple[InMemoryBackupStore, UUID]:
    store = InMemoryBackupStore()
    summary = await ExportUserData(
        store,
        snapshot,
        InMemoryMediaFiles(),
        InMemoryAccessGuard(),
        app_version="test",
    ).handle(ExportUserDataCommand(), actor)
    return store, summary.id


async def _import(
    store: InMemoryBackupStore, backup_id: UUID, actor: Actor
) -> InMemoryUserDatabaseRestorer:
    restorer = InMemoryUserDatabaseRestorer("rev")
    await ImportUserData(
        store,
        restorer,
        InMemoryMediaFiles(),
        InMemoryBackupWorkspace(),
        InMemoryAccessGuard(),
    ).handle(ImportUserDataCommand(backup_id=backup_id), actor)
    return restorer


async def test_links_round_trip_to_the_importer_keeping_entity_ids() -> None:
    """Links come back owned by the importer, pointing at the same item ids."""
    mine, other = Actor(id=uuid7()), Actor(id=uuid7())
    item_id = uuid7()
    tables = _tables(mine, other, item_id, uuid7())
    store, backup_id = await _export(InMemoryUserDatabaseSnapshot("rev", tables), mine)
    importer = Actor(id=uuid7())

    restorer = await _import(store, backup_id, importer)

    [link] = restorer.tables["source_links"]
    assert str(link["owner_id"]) == str(importer.id)
    assert str(link["entity_id"]) == str(item_id)
    assert (link["source"], link["key"]) == ("lddb", "k1")


async def test_another_persons_links_are_not_exported() -> None:
    """The archive holds only the exporter's own links."""
    mine, other = Actor(id=uuid7()), Actor(id=uuid7())
    tables = _tables(mine, other, uuid7(), uuid7())
    store, backup_id = await _export(InMemoryUserDatabaseSnapshot("rev", tables), mine)

    payload = b"".join(store.members[backup_id].values())

    assert b"k-private" not in payload


async def test_an_archive_from_before_source_links_still_imports() -> None:
    """An export made before links existed has no links table, and imports."""
    mine, other = Actor(id=uuid7()), Actor(id=uuid7())
    tables = _tables(mine, other, uuid7(), uuid7())
    store, backup_id = await _export(_SnapshotWithoutLinks("rev", tables), mine)
    importer = Actor(id=uuid7())

    restorer = await _import(store, backup_id, importer)

    assert restorer.tables["nodes"][0]["name"] == "Alien"
    assert restorer.tables.get("source_links", []) == []
