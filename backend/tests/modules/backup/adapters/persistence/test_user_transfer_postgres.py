import json
from uuid import uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.entrypoints.api.shared.bridges.backup_user_validator import (
    BackupUserImportValidator,
)
from app.modules.backup.adapters.persistence.user_database_restorer import (
    SqlAlchemyUserDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.user_database_snapshot import (
    SqlAlchemyUserDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_reader import (
    InMemoryBackupReader,
)
from app.modules.backup.domain.errors import ImportCollisionError
from app.shared_kernel.content_filter import ContentFilter

pytestmark = pytest.mark.integration


async def test_reflected_user_transfer_keeps_other_accounts(
    snapshot_database: str,
) -> None:
    """SQL exports isolate owners and import preserves ids with a new owner."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    owner, other, destination, item, private, type_id = (uuid7() for _ in range(6))
    try:
        async with engine.begin() as connection:
            for identifier, username in (
                (owner, "owner"),
                (other, "other"),
                (destination, "destination"),
            ):
                await connection.execute(
                    text("""INSERT INTO users
                    (id, username, display_name, password_hash, role,
                    password_expired, disabled, created_at, updated_at)
                    VALUES (:id, :name, :name, 'secret-hash', 'member',
                    false, false, now(), now())"""),
                    {"id": identifier, "name": username},
                )
            await connection.execute(
                text("""INSERT INTO node_types
                (id, slug, label, attributes_schema, created_at, updated_at)
                VALUES (:id,'book','Book',NULL,now(),now())"""),
                {"id": type_id},
            )
            for identifier, user_id, name in (
                (item, owner, "Mine"),
                (private, other, "Private"),
            ):
                await connection.execute(
                    text("""INSERT INTO nodes
                    (id, owner_id, name, type, attributes, tags,
                    created_at, updated_at)
                    VALUES (:id,:owner,:name,'book','{}','[]',now(),now())"""),
                    {"id": identifier, "owner": user_id, "name": name},
                )
            for user_id, node_id in ((owner, item), (other, item), (other, private)):
                await connection.execute(
                    text("""INSERT INTO node_favourites (user_id, node_id, created_at)
                    VALUES (:user, :node, now())"""),
                    {"user": user_id, "node": node_id},
                )
        snapshot = SqlAlchemyUserDatabaseSnapshot(factory)
        members = {
            member.name: b"".join([chunk async for chunk in member.chunks])
            async for member in snapshot.export(scope=ContentFilter.of(owner))
        }
        assert b"secret-hash" not in b"".join(members.values())
        assert b"Private" not in b"".join(members.values())
        assert "data/users.ndjson" not in members
        assert json.loads(members["data/nodes.ndjson"])["id"] == str(item)
        starred = [
            json.loads(line)
            for line in members["data/node_favourites.ndjson"].splitlines()
        ]
        assert [(row["user_id"], row["node_id"]) for row in starred] == [
            (str(owner), str(item))
        ]
        restorer = SqlAlchemyUserDatabaseRestorer(factory, BackupUserImportValidator())
        with pytest.raises(ImportCollisionError):
            await restorer.import_user(
                InMemoryBackupReader(members).members(), new_owner_id=destination
            )
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM nodes WHERE id=:id"), {"id": item}
            )
        await restorer.import_user(
            InMemoryBackupReader(members).members(), new_owner_id=destination
        )
        async with engine.connect() as connection:
            assert (
                await connection.scalar(
                    text("SELECT owner_id FROM nodes WHERE id=:id"), {"id": item}
                )
                == destination
            )
            assert (
                await connection.scalar(
                    text("SELECT owner_id FROM nodes WHERE id=:id"), {"id": private}
                )
                == other
            )
            favourites = (
                await connection.execute(
                    text("SELECT user_id, node_id FROM node_favourites")
                )
            ).all()
            # The import gives the item's star to the importing account; the other
            # person's stars on their own item are untouched.
            assert {(row.user_id, row.node_id) for row in favourites} == {
                (destination, item),
                (other, private),
            }
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 3
    finally:
        await engine.dispose()


async def test_presets_export_whole_and_import_without_reusing_donor_rows(
    snapshot_database: str,
) -> None:
    """All of a person's live presets travel; the importer's copies are its own."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    owner, other, destination = uuid7(), uuid7(), uuid7()
    used, unused, deleted, theirs = (uuid7() for _ in range(4))
    try:
        async with engine.begin() as connection:
            for identifier, username in (
                (owner, "owner"),
                (other, "other"),
                (destination, "destination"),
            ):
                await connection.execute(
                    text("""INSERT INTO users
                    (id, username, display_name, password_hash, role,
                    password_expired, disabled, created_at, updated_at)
                    VALUES (:id, :name, :name, 'hash', 'member',
                    false, false, now(), now())"""),
                    {"id": identifier, "name": username},
                )
            for identifier, user_id, label, gone in (
                (used, owner, "Used", False),
                (unused, owner, "Unused", False),
                (deleted, owner, "Deleted", True),
                (theirs, other, "Theirs", False),
            ):
                await connection.execute(
                    text("""INSERT INTO presets
                    (id, owner_id, kind, label, definition, version,
                    created_at, updated_at, deleted_at)
                    VALUES (:id, :owner, 'choice_list', :label,
                    '{"options": ["a"]}', 1, now(), now(),
                    CASE WHEN :gone THEN now() END)"""),
                    {"id": identifier, "owner": user_id, "label": label, "gone": gone},
                )
        members = {
            member.name: b"".join([chunk async for chunk in member.chunks])
            async for member in SqlAlchemyUserDatabaseSnapshot(factory).export(
                scope=ContentFilter.of(owner)
            )
        }
        exported = {
            json.loads(line)["id"]
            for line in members["data/presets.ndjson"].splitlines()
        }
        assert exported == {str(used), str(unused)}
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM presets WHERE id IN (:a, :b)"),
                {"a": used, "b": unused},
            )
            await connection.execute(
                text("""INSERT INTO presets
                (id, owner_id, kind, label, definition, version,
                created_at, updated_at)
                VALUES (:id, :owner, 'choice_list', 'Used',
                '{"options": ["a"]}', 1, now(), now())"""),
                {"id": uuid7(), "owner": other},
            )
        restorer = SqlAlchemyUserDatabaseRestorer(factory, BackupUserImportValidator())
        await restorer.import_user(
            InMemoryBackupReader(members).members(), new_owner_id=destination
        )
        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text("SELECT id, owner_id, label FROM presets ORDER BY label")
                )
            ).all()
        assert {(row.id, row.owner_id) for row in rows} >= {
            (used, destination),
            (unused, destination),
        }
        # The other person's identical "Used" list was not linked to.
        assert sum(row.label == "Used" for row in rows) == 2
    finally:
        await engine.dispose()
