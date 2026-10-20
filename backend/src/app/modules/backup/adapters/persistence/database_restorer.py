"""Transactional logical restore into the reflected instance schema."""

import json
from typing import TYPE_CHECKING

from sqlalchemy import JSON, MetaData, delete, func, insert, select, text

from app.modules.backup.adapters.persistence.row_codec import decode_row
from app.modules.backup.adapters.persistence.table_rules import TableRule, table_rule
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    RestoreTargetNotEmptyError,
)
from app.platform.advisory_locks import SETUP_LOCK_KEY
from app.platform.alembic_runner import db_current_revisions

MAX_ROW_BYTES = 16 * 1024 * 1024


def _check_row_size(size: int) -> None:
    if size > MAX_ROW_BYTES:
        raise CorruptBackupError("Backup row exceeds the size limit.")


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

    from app.modules.backup.ports.archive_member import ArchiveMember


class SqlAlchemyDatabaseRestorer:
    """Replace instance rows atomically without changing the migration revision."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def schema_revision(self) -> str:
        """Return the target database's sorted migration revisions."""
        return ",".join(sorted(await db_current_revisions(self._session_factory)))

    @staticmethod
    async def _tables(connection: AsyncConnection) -> list[Table]:
        metadata = MetaData()
        await connection.run_sync(metadata.reflect)
        tables = list(metadata.sorted_tables)
        for table in tables:
            table_rule(table.name)
            for column in table.c:
                if isinstance(column.type, JSON):
                    column.type.none_as_null = True
        return tables

    @staticmethod
    async def _is_empty(connection: AsyncConnection, tables: list[Table]) -> bool:
        for table in tables:
            if table_rule(table.name) is not TableRule.KEEP:
                continue
            query = select(table)
            if table.name == "presets":
                query = query.where(table.c.builtin.is_(False))
            if await connection.scalar(select(query.exists())):
                return False
        return True

    async def is_empty(self) -> bool:
        """Ignore seeded builtin presets when checking for instance content."""
        async with self._session_factory() as session:
            connection = await session.connection()
            return await self._is_empty(connection, await self._tables(connection))

    async def restore_instance(
        self,
        members: AsyncIterator[ArchiveMember],
        *,
        replace: bool,
        setup_only: bool,
    ) -> None:
        """Load all kept tables in one transaction, clearing transient sign-in data."""
        async with self._session_factory() as session, session.begin():
            connection = await session.connection()
            if setup_only:
                await connection.execute(
                    select(func.pg_advisory_xact_lock(SETUP_LOCK_KEY))
                )
            tables = await self._tables(connection)
            mutable = [
                table
                for table in tables
                if table_rule(table.name) is not TableRule.IGNORE
            ]
            # Block concurrent writes between the emptiness check and commit.
            names = ", ".join(
                connection.dialect.identifier_preparer.format_table(table)
                for table in mutable
            )
            await connection.execute(text(f"LOCK TABLE {names} IN EXCLUSIVE MODE"))
            if (setup_only or not replace) and not await self._is_empty(
                connection, tables
            ):
                raise RestoreTargetNotEmptyError("The restore target is not empty.")
            for table in reversed(mutable):
                await connection.execute(delete(table))
            expected = {
                f"data/{table.name}.ndjson": table
                for table in tables
                if table_rule(table.name) is TableRule.KEEP
            }
            seen: set[str] = set()
            async for member in members:
                if member.name not in expected or member.name in seen:
                    raise CorruptBackupError(
                        f"Unexpected or duplicate restore table: {member.name}"
                    )
                seen.add(member.name)
                await self._load(connection, expected[member.name], member.chunks)
            if seen != expected.keys():
                raise CorruptBackupError(
                    f"Missing restore tables: {sorted(expected.keys() - seen)}"
                )

    @staticmethod
    async def _load(
        connection: AsyncConnection, table: Table, chunks: AsyncIterator[bytes]
    ) -> None:
        pending = bytearray()
        rows: list[dict[str, object]] = []
        async for chunk in chunks:
            pending.extend(chunk)
            while (end := pending.find(b"\n")) != -1:
                _check_row_size(end)
                line = bytes(pending[:end])
                del pending[: end + 1]
                try:
                    value: object = json.loads(line)
                    if not isinstance(value, dict):
                        raise CorruptBackupError("Backup rows must be JSON objects.")
                    row = decode_row(value, table)
                except (ValueError, UnicodeError, TypeError) as exc:
                    raise CorruptBackupError(
                        f"Invalid backup row in {table.name!r}."
                    ) from exc
                if rows and (len(rows) >= 500 or rows[0].keys() != row.keys()):
                    await connection.execute(insert(table), rows)
                    rows.clear()
                rows.append(row)
            _check_row_size(len(pending))
        if pending:
            raise CorruptBackupError(f"Unterminated backup row in {table.name!r}.")
        if rows:
            await connection.execute(insert(table), rows)
