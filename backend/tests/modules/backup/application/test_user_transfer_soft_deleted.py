import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from uuid import uuid7

from app.modules.backup.adapters.persistence.in_memory_user_database_restorer import (
    InMemoryUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.in_memory_user_database_snapshot import (
    InMemoryUserDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.row_codec import encode_row
from app.modules.backup.adapters.persistence.user_transfer_rows import USER_TABLES
from app.modules.backup.ports.archive_member import ArchiveMember
from app.shared_kernel.content_filter import ContentFilter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

STAMP = datetime(2026, 1, 1, tzinfo=UTC).isoformat()


async def test_export_leaves_out_soft_deleted_content() -> None:
    """Soft-deleted items, connections and collections, and rows hanging off them."""
    owner = uuid7()
    live, live2, gone, shelf, old_shelf = (uuid7() for _ in range(5))
    tables: dict[str, list[dict[str, object]]] = {
        "nodes": [
            {"id": live, "owner_id": owner, "deleted_at": None},
            {"id": live2, "owner_id": owner, "deleted_at": None},
            {"id": gone, "owner_id": owner, "deleted_at": STAMP},
        ],
        "edges": [
            {
                "id": (kept := uuid7()),
                "owner_id": owner,
                "deleted_at": None,
                "source_id": live,
                "target_id": live2,
            },
            {
                "id": uuid7(),
                "owner_id": owner,
                "deleted_at": None,
                "source_id": live,
                "target_id": gone,
            },
            {
                "id": uuid7(),
                "owner_id": owner,
                "deleted_at": STAMP,
                "source_id": live,
                "target_id": live2,
            },
        ],
        "collections": [
            {"id": shelf, "owner_id": owner, "deleted_at": None},
            {"id": old_shelf, "owner_id": owner, "deleted_at": STAMP},
        ],
        "collection_members": [
            {"collection_id": shelf, "item_id": live},
            {"collection_id": shelf, "item_id": gone},
            {"collection_id": old_shelf, "item_id": live},
        ],
    }

    snapshot = InMemoryUserDatabaseSnapshot("rev", tables)
    members = {
        m.name: b"".join([c async for c in m.chunks])
        async for m in snapshot.export(scope=ContentFilter.of(owner))
    }

    def ids(table: str, key: str = "id") -> set[str]:
        lines = members[f"data/{table}.ndjson"].splitlines()
        return {json.loads(line)[key] for line in lines}

    assert ids("nodes") == {str(live), str(live2)}
    assert ids("edges") == {str(kept)}
    assert ids("collections") == {str(shelf)}
    assert ids("collection_members", "item_id") == {str(live)}


async def test_import_ignores_soft_deleted_rows_and_their_dependants() -> None:
    """An old archive with soft-deleted rows imports without error, minus those."""
    live, live2, gone, shelf, old_shelf = (uuid7() for _ in range(5))
    rows: dict[str, list[dict[str, object]]] = {name: [] for name in USER_TABLES}
    rows["nodes"] = [
        {"id": str(live), "deleted_at": None},
        {"id": str(live2), "deleted_at": None},
        {"id": str(gone), "deleted_at": STAMP},
    ]
    rows["edges"] = [
        {
            "id": str(uuid7()),
            "deleted_at": None,
            "source_id": str(live),
            "target_id": str(live2),
        },
        {
            "id": str(uuid7()),
            "deleted_at": None,
            "source_id": str(live),
            "target_id": str(gone),
        },
        {
            "id": str(uuid7()),
            "deleted_at": STAMP,
            "source_id": str(live),
            "target_id": str(live2),
        },
    ]
    rows["collections"] = [
        {"id": str(shelf), "deleted_at": None},
        {"id": str(old_shelf), "deleted_at": STAMP},
    ]
    rows["collection_members"] = [
        {"collection_id": str(shelf), "item_id": str(live)},
        {"collection_id": str(shelf), "item_id": str(gone)},
        {"collection_id": str(old_shelf), "item_id": str(live)},
    ]
    rows["media_assets"] = [{"id": str(uuid7())}]
    rows["media_attachments"] = [
        {
            "id": str(uuid7()),
            "asset_id": rows["media_assets"][0]["id"],
            "target_type": "node",
            "target_id": str(gone),
        },
    ]

    async def one(data: bytes) -> AsyncIterator[bytes]:
        yield data

    async def stream() -> AsyncIterator[ArchiveMember]:
        for name in USER_TABLES:
            data = b"".join(encode_row(r) for r in rows[name])
            yield ArchiveMember(name=f"data/{name}.ndjson", chunks=one(data))

    restorer = InMemoryUserDatabaseRestorer("rev")
    await restorer.import_user(stream(), new_owner_id=uuid7())

    assert {str(r["id"]) for r in restorer.tables["nodes"]} == {str(live), str(live2)}
    assert len(restorer.tables["edges"]) == 1
    assert [str(r["id"]) for r in restorer.tables["collections"]] == [str(shelf)]
    assert [str(r["item_id"]) for r in restorer.tables["collection_members"]] == [
        str(live)
    ]
    assert restorer.tables["media_attachments"] == []
