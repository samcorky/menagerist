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
from app.shared_kernel.access_scope import AccessScope

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
                    (id, owner_id, name, type, attributes, favourite, tags,
                    created_at, updated_at)
                    VALUES (:id,:owner,:name,'book','{}',false,'[]',now(),now())"""),
                    {"id": identifier, "owner": user_id, "name": name},
                )
        snapshot = SqlAlchemyUserDatabaseSnapshot(factory)
        members = {
            member.name: b"".join([chunk async for chunk in member.chunks])
            async for member in snapshot.export(scope=AccessScope.of(owner))
        }
        assert b"secret-hash" not in b"".join(members.values())
        assert b"Private" not in b"".join(members.values())
        assert "data/users.ndjson" not in members
        assert json.loads(members["data/nodes.ndjson"])["id"] == str(item)
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
            assert await connection.scalar(text("SELECT count(*) FROM users")) == 3
    finally:
        await engine.dispose()
