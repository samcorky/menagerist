import json
from datetime import UTC, datetime
from uuid import UUID, uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.bridges.backup_user_validator import (
    BackupUserImportValidator,
)
from app.modules.backup.adapters.persistence.row_codec import encode_row
from app.modules.backup.adapters.persistence.user_database_restorer import (
    SqlAlchemyUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.user_database_snapshot import (
    SqlAlchemyUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_reader import (
    InMemoryBackupReader,
)
from app.shared_kernel.content_filter import ContentFilter

pytestmark = pytest.mark.integration

_NODE = """INSERT INTO nodes
    (id, owner_id, name, type, attributes, favourite, tags,
     created_at, updated_at, deleted_at)
    VALUES (:id, :owner, :name, NULL, '{}', false, '[]', now(), now(), :deleted)"""
_EDGE = """INSERT INTO edges
    (id, owner_id, source_id, target_id, type, attributes,
     created_at, updated_at, deleted_at)
    VALUES (:id, :owner, :source, :target, 'rel', '{}', now(), now(), :deleted)"""
_COLLECTION = """INSERT INTO collections
    (id, owner_id, name, slug, kind, visibility, created_at, updated_at, deleted_at)
    VALUES (:id, :owner, :name, :name, 'manual', 'private', now(), now(), :deleted)"""
_MEMBER = """INSERT INTO collection_members (collection_id, item_id, added_at)
    VALUES (:collection, :item, now())"""
_DELETED = datetime(2026, 1, 1, tzinfo=UTC)
_STAMP = _DELETED.isoformat()


async def _ids(connection, table: str) -> set[UUID]:  # type: ignore[no-untyped-def]  # noqa: ANN001
    return {r[0] for r in await connection.execute(text(f"SELECT id FROM {table}"))}


async def test_export_skips_soft_deleted_rows_and_import_skips_old_ones(
    snapshot_database: str,
) -> None:
    """Soft-deleted content is not exported; an old archive holding it still imports."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    owner, destination = uuid7(), uuid7()
    live, live2, gone, shelf, old_shelf = (uuid7() for _ in range(5))
    live_edge, to_gone_edge, gone_edge = uuid7(), uuid7(), uuid7()
    try:
        async with engine.begin() as connection:
            for identifier, name in ((owner, "owner"), (destination, "destination")):
                await connection.execute(
                    text("""INSERT INTO users
                    (id, username, display_name, password_hash, role,
                    password_expired, disabled, created_at, updated_at)
                    VALUES (:id, :name, :name, 'h', 'member', false, false,
                    now(), now())"""),
                    {"id": identifier, "name": name},
                )
            for identifier, name, deleted in (
                (live, "live", None),
                (live2, "live2", None),
                (gone, "gone", _DELETED),
            ):
                await connection.execute(
                    text(_NODE),
                    {
                        "id": identifier,
                        "owner": owner,
                        "name": name,
                        "deleted": deleted,
                    },
                )
            for identifier, source, target, deleted in (
                (live_edge, live, live2, None),
                (to_gone_edge, live, gone, None),
                (gone_edge, live, live2, _DELETED),
            ):
                await connection.execute(
                    text(_EDGE),
                    {
                        "id": identifier,
                        "owner": owner,
                        "source": source,
                        "target": target,
                        "deleted": deleted,
                    },
                )
            for identifier, name, deleted in (
                (shelf, "shelf", None),
                (old_shelf, "old", _DELETED),
            ):
                await connection.execute(
                    text(_COLLECTION),
                    {
                        "id": identifier,
                        "owner": owner,
                        "name": name,
                        "deleted": deleted,
                    },
                )
            for collection, item in (
                (shelf, live),
                (shelf, gone),
                (old_shelf, live),
            ):
                await connection.execute(
                    text(_MEMBER), {"collection": collection, "item": item}
                )

        snapshot = SqlAlchemyUserDatabaseSnapshot(factory)
        members = {
            member.name: b"".join([chunk async for chunk in member.chunks])
            async for member in snapshot.export(scope=ContentFilter.of(owner))
        }

        def exported(table: str) -> list[dict[str, object]]:
            data = members[f"data/{table}.ndjson"]
            return [json.loads(line) for line in data.splitlines()]

        assert {r["id"] for r in exported("nodes")} == {str(live), str(live2)}
        assert {r["id"] for r in exported("edges")} == {str(live_edge)}
        assert {r["id"] for r in exported("collections")} == {str(shelf)}
        assert {
            (r["collection_id"], r["item_id"]) for r in exported("collection_members")
        } == {(str(shelf), str(live))}

        # An archive from before this change still carries the soft-deleted rows.
        node_row, edge_row, shelf_row = (
            exported("nodes")[0],
            exported("edges")[0],
            exported("collections")[0],
        )
        extra: dict[str, list[dict[str, object]]] = {
            "data/nodes.ndjson": [{**node_row, "id": str(gone), "deleted_at": _STAMP}],
            "data/edges.ndjson": [
                {**edge_row, "id": str(to_gone_edge), "target_id": str(gone)},
                {**edge_row, "id": str(gone_edge), "deleted_at": _STAMP},
            ],
            "data/collections.ndjson": [
                {
                    **shelf_row,
                    "id": str(old_shelf),
                    "slug": "old",
                    "deleted_at": _STAMP,
                }
            ],
            "data/collection_members.ndjson": [
                {"collection_id": str(shelf), "item_id": str(gone), "added_at": _STAMP},
                {
                    "collection_id": str(old_shelf),
                    "item_id": str(live),
                    "added_at": _STAMP,
                },
            ],
        }
        old = {
            name: data + b"".join(encode_row(r) for r in extra.get(name, []))
            for name, data in members.items()
        }
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM collection_members"))
            await connection.execute(text("DELETE FROM edges"))
            await connection.execute(text("DELETE FROM collections"))
            await connection.execute(text("DELETE FROM nodes"))
        restorer = SqlAlchemyUserDatabaseRestorer(factory, BackupUserImportValidator())

        await restorer.import_user(
            InMemoryBackupReader(old).members(), new_owner_id=destination
        )

        async with engine.connect() as connection:
            assert await _ids(connection, "nodes") == {live, live2}
            assert await _ids(connection, "edges") == {live_edge}
            assert await _ids(connection, "collections") == {shelf}
            members_left = await connection.execute(
                text("SELECT collection_id, item_id FROM collection_members")
            )
            assert {tuple(r) for r in members_left} == {(shelf, live)}
    finally:
        await engine.dispose()
