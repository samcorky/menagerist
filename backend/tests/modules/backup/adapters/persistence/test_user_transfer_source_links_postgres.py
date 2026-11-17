"""Source links in the reflected personal export and import."""

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
from app.shared_kernel.content_filter import ContentFilter

pytestmark = pytest.mark.integration


async def test_links_export_for_the_owner_only_and_import_to_the_destination(
    snapshot_database: str,
) -> None:
    """A person's links keep their item ids and become the importer's own."""
    engine = create_async_engine(snapshot_database)
    factory = async_sessionmaker(engine)
    owner, other, destination, item, private = (uuid7() for _ in range(5))
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
            for node_id, user_id in ((item, owner), (private, other)):
                await connection.execute(
                    text("""INSERT INTO nodes
                    (id, owner_id, name, attributes, tags, created_at, updated_at)
                    VALUES (:id, :owner, 'n', '{}', '[]', now(), now())"""),
                    {"id": node_id, "owner": user_id},
                )
                await connection.execute(
                    text("""INSERT INTO source_links
                    (id, owner_id, source, kind, key, entity_id, fields,
                    imported_at, created_at, updated_at)
                    VALUES (:id, :owner, 'lddb', 'item', :key, :entity,
                    '{"name": "h"}', now(), now(), now())"""),
                    {
                        "id": uuid7(),
                        "owner": user_id,
                        "key": f"k-{user_id}",
                        "entity": node_id,
                    },
                )
        members = {
            member.name: b"".join([chunk async for chunk in member.chunks])
            async for member in SqlAlchemyUserDatabaseSnapshot(factory).export(
                scope=ContentFilter.of(owner)
            )
        }
        exported = [
            json.loads(line)
            for line in members["data/source_links.ndjson"].splitlines()
        ]
        assert [row["entity_id"] for row in exported] == [str(item)]
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM source_links WHERE owner_id=:o"), {"o": owner}
            )
            await connection.execute(
                text("DELETE FROM nodes WHERE id=:id"), {"id": item}
            )

        restorer = SqlAlchemyUserDatabaseRestorer(factory, BackupUserImportValidator())
        await restorer.import_user(
            InMemoryBackupReader(members).members(), new_owner_id=destination
        )

        async with engine.connect() as connection:
            rows = (
                await connection.execute(
                    text("SELECT owner_id, entity_id, fields FROM source_links")
                )
            ).all()
        assert {(row.owner_id, row.entity_id) for row in rows} == {
            (destination, item),
            (other, private),
        }
    finally:
        await engine.dispose()
