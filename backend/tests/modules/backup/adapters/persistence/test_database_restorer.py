import asyncio
import json
from typing import TYPE_CHECKING
from uuid import uuid7

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.modules.backup.adapters.persistence.database_restorer import (
    SqlAlchemyDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.database_snapshot import (
    SqlAlchemyDatabaseSnapshot,
)
from app.modules.backup.adapters.storage.in_memory_backup_reader import byte_chunks
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    RestoreTargetNotEmptyError,
)
from app.modules.backup.ports.archive_member import ArchiveMember
from app.platform.advisory_locks import SETUP_LOCK_KEY

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = pytest.mark.integration


async def _capture(engine: AsyncEngine) -> dict[str, bytes]:
    snapshot = SqlAlchemyDatabaseSnapshot(async_sessionmaker(engine))
    return {
        member.name: b"".join([chunk async for chunk in member.chunks])
        async for member in snapshot.export()
    }


async def _members(tables: dict[str, bytes]) -> AsyncIterator[ArchiveMember]:
    for name, content in tables.items():
        # Exercise rows split across chunks, including inside UTF-8 characters.
        async def chunks(data: bytes = content) -> AsyncIterator[bytes]:
            for offset in range(0, len(data), 7):
                yield data[offset : offset + 7]

        yield ArchiveMember(name=name, chunks=chunks())


async def _seed(engine: AsyncEngine) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            text("""INSERT INTO users
                (id, username, display_name, password_hash, role,
                 password_expired, disabled, created_at, updated_at) VALUES
                (:id, 'archived', 'Café administrator', 'hash', 'admin',
                 false, false, now(), now())"""),
            {"id": uuid7()},
        )
        await connection.execute(
            text("""INSERT INTO nodes
                (id, owner_id, name, attributes, favourite, tags,
                 created_at, updated_at, deleted_at)
                SELECT :id, id, 'Archived item', '{"nested": [true, null]}',
                false, '[]', now(), now(), now() FROM users"""),
            {"id": uuid7()},
        )


async def test_restore_round_trip_and_clear_sessions(snapshot_database: str) -> None:
    """Replacement preserves content and revision but invalidates sign-ins."""
    engine = create_async_engine(snapshot_database)
    try:
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        assert await restorer.is_empty()  # Seeded builtin presets are allowed.
        revision = await restorer.schema_revision()
        await _seed(engine)
        assert not await restorer.is_empty()
        original = await _capture(engine)
        async with engine.begin() as connection:
            await connection.execute(text("UPDATE users SET username = 'changed'"))
            await connection.execute(
                text("""INSERT INTO sessions
                (id, user_id, token_hash, created_at, expires_at, last_seen_at)
                SELECT :id, id, 'token', now(), now(), now() FROM users"""),
                {"id": uuid7()},
            )
            await connection.execute(
                text("""INSERT INTO sign_in_attempts
                (key_type, key_hash, failure_count, window_start)
                VALUES ('ip', 'hash', 1, now())""")
            )
        await restorer.restore_instance(
            _members(original), replace=True, setup_only=False
        )
        assert await _capture(engine) == original
        assert await restorer.schema_revision() == revision
        async with engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT extra_schema IS NULL FROM nodes")
            )
            assert await connection.scalar(text("SELECT count(*) FROM sessions")) == 0
            assert (
                await connection.scalar(text("SELECT count(*) FROM sign_in_attempts"))
                == 0
            )
    finally:
        await engine.dispose()


@pytest.mark.parametrize(("replace", "setup_only"), [(False, False), (True, True)])
async def test_non_empty_target_is_unchanged(
    snapshot_database: str, replace: bool, setup_only: bool
) -> None:
    """First-run restore cannot overwrite accounts even with replacement requested."""
    engine = create_async_engine(snapshot_database)
    try:
        await _seed(engine)
        original = await _capture(engine)
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        with pytest.raises(RestoreTargetNotEmptyError):
            await restorer.restore_instance(
                _members(original), replace=replace, setup_only=setup_only
            )
        assert await _capture(engine) == original
    finally:
        await engine.dispose()


def _damage(tables: dict[str, bytes], damage: str) -> None:
    payloads = {
        "json": b"not json\n",
        "array": b"[]\n",
        "unterminated": tables["data/users.ndjson"].rstrip(b"\n"),
        "uuid": tables["data/users.ndjson"].replace(b'"id": "', b'"id": "bad'),
    }
    if damage in payloads:
        tables["data/users.ndjson"] = payloads[damage]
    elif damage == "column":
        row = json.loads(tables["data/users.ndjson"])
        row["surprise"] = True
        tables["data/users.ndjson"] = json.dumps(row).encode() + b"\n"
    elif damage == "missing":
        del tables["data/nodes.ndjson"]
    elif damage in {"unknown", "sessions"}:
        tables[f"data/{damage}.ndjson"] = b"{}\n"


@pytest.mark.parametrize(
    "damage",
    [
        "stream",
        "json",
        "array",
        "unterminated",
        "uuid",
        "column",
        "missing",
        "duplicate",
        "unknown",
        "sessions",
    ],
)
async def test_failed_replacement_rolls_back(
    snapshot_database: str, damage: str
) -> None:
    """A failed load leaves the original rows intact."""
    engine = create_async_engine(snapshot_database)
    try:
        await _seed(engine)
        original = await _capture(engine)
        damaged = dict(original)
        _damage(damaged, damage)

        async def failing_members() -> AsyncIterator[ArchiveMember]:
            async for member in _members(damaged):
                yield member
            if damage == "stream":
                raise OSError("input failed")
            if damage == "duplicate":
                yield ArchiveMember(name="data/users.ndjson", chunks=byte_chunks(b""))

        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        expected = OSError if damage == "stream" else CorruptBackupError
        with pytest.raises(expected):
            await restorer.restore_instance(
                failing_members(), replace=True, setup_only=False
            )
        assert await _capture(engine) == original
    finally:
        await engine.dispose()


async def test_restore_into_fresh_target(snapshot_database: str) -> None:
    """First-run loading replaces seeded presets without primary-key collisions."""
    engine = create_async_engine(snapshot_database)
    try:
        await _seed(engine)
        original = await _capture(engine)
        async with engine.begin() as connection:
            await connection.execute(text("DELETE FROM nodes"))
            await connection.execute(text("DELETE FROM users"))
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        await restorer.restore_instance(
            _members(original), replace=False, setup_only=True
        )
        assert await _capture(engine) == original
    finally:
        await engine.dispose()


async def test_json_null_and_sql_null_remain_distinct(snapshot_database: str) -> None:
    """Root JSON null and SQL NULL retain their database predicates after restore."""
    engine = create_async_engine(snapshot_database)
    try:
        await _seed(engine)
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE nodes SET extra_schema = 'null'::jsonb")
            )
        original = await _capture(engine)
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        await restorer.restore_instance(
            _members(original), replace=True, setup_only=False
        )
        async with engine.connect() as connection:
            assert await connection.scalar(
                text("SELECT extra_schema = 'null'::jsonb FROM nodes")
            )
            assert not await connection.scalar(
                text("SELECT extra_schema IS NULL FROM nodes")
            )
        assert await _capture(engine) == original
    finally:
        await engine.dispose()


async def test_multiple_batches_restore_all_rows(snapshot_database: str) -> None:
    """A load larger than a batch preserves every row and nested JSON."""
    engine = create_async_engine(snapshot_database)
    try:
        await _seed(engine)
        original = await _capture(engine)
        row = json.loads(original["data/nodes.ndjson"])
        rows = []
        for number in range(1002):
            rows.append({**row, "id": str(uuid7()), "name": f"Item {number}"})
        del rows[1]["deleted_at"]
        original["data/nodes.ndjson"] = b"".join(
            json.dumps(item).encode() + b"\n" for item in rows
        )
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        await restorer.restore_instance(
            _members(original), replace=True, setup_only=False
        )
        restored = await _capture(engine)
        assert {
            json.loads(line)["name"]
            for line in restored["data/nodes.ndjson"].splitlines()
        } == {f"Item {number}" for number in range(1002)}
        assert all(
            json.loads(line)["attributes"] == {"nested": [True, None]}
            for line in restored["data/nodes.ndjson"].splitlines()
        )
    finally:
        await engine.dispose()


async def test_constraint_failure_rolls_back(snapshot_database: str) -> None:
    """A database constraint failure rolls back deletion and partially loaded rows."""
    engine = create_async_engine(snapshot_database)
    try:
        await _seed(engine)
        original = await _capture(engine)
        damaged = dict(original)
        row = json.loads(damaged["data/nodes.ndjson"])
        row["name"] = None
        damaged["data/nodes.ndjson"] = json.dumps(row).encode() + b"\n"
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        with pytest.raises(IntegrityError):
            await restorer.restore_instance(
                _members(damaged), replace=True, setup_only=False
            )
        assert await _capture(engine) == original
    finally:
        await engine.dispose()


async def test_unclassified_target_table_is_refused(snapshot_database: str) -> None:
    """A future table cannot be silently cleared or excluded from restoration."""
    engine = create_async_engine(snapshot_database)
    try:
        original = await _capture(engine)
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE future_table (id integer)"))
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        with pytest.raises(CorruptBackupError, match="future_table"):
            await restorer.restore_instance(
                _members(original), replace=True, setup_only=False
            )
    finally:
        await engine.dispose()


async def test_first_run_restore_waits_for_setup(snapshot_database: str) -> None:
    """An in-flight setup can win; restore then refuses the new account."""
    engine = create_async_engine(snapshot_database)
    task: asyncio.Task[None] | None = None
    try:
        original = await _capture(engine)
        restorer = SqlAlchemyDatabaseRestorer(async_sessionmaker(engine))
        async with engine.begin() as connection:
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": SETUP_LOCK_KEY}
            )
            task = asyncio.create_task(
                restorer.restore_instance(
                    _members(original), replace=False, setup_only=True
                )
            )
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), timeout=0.25)
            await _seed(engine)
        with pytest.raises(RestoreTargetNotEmptyError):
            await asyncio.wait_for(task, timeout=5)
        async with engine.connect() as connection:
            assert (
                await connection.scalar(text("SELECT username FROM users"))
                == "archived"
            )
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await engine.dispose()
