"""Streaming logical snapshots of the live database, including older schemas."""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, MetaData, select

from app.modules.backup.adapters.persistence.row_codec import encode_row
from app.modules.backup.adapters.persistence.table_rules import TableRule, table_rule
from app.modules.backup.ports.archive_member import ArchiveMember
from app.platform.alembic_runner import db_current_revisions

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker


class SqlAlchemyDatabaseSnapshot:
    """Export reflected tables within one repeatable, read-only transaction."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def schema_revision(self) -> str:
        """Return the database's current revisions, sorted and comma-separated."""
        return ",".join(sorted(await db_current_revisions(self._session_factory)))

    async def export(self) -> AsyncGenerator[ArchiveMember]:
        """Yield every kept table in reflected foreign-key order."""
        async with self._session_factory() as session:
            connection = await session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
            metadata = MetaData()
            await connection.run_sync(metadata.reflect)
            tables = metadata.sorted_tables
            for table in tables:
                table_rule(table.name)
            for table in tables:
                if table_rule(table.name) is TableRule.KEEP:
                    yield ArchiveMember(
                        name=f"data/{table.name}.ndjson",
                        chunks=self._rows(connection, table),
                    )

    @staticmethod
    async def _rows(connection: AsyncConnection, table: Table) -> AsyncIterator[bytes]:
        json_columns = [column for column in table.c if isinstance(column.type, JSON)]
        async with connection.stream(
            select(
                table,
                *(
                    column.is_(None).label(f"$null_{column.name}")
                    for column in json_columns
                ),
            ).execution_options(yield_per=1000)
        ) as result:
            async for row in result.mappings():
                values = {column.name: row[column.name] for column in table.c}
                json_nulls = [
                    column.name
                    for column in json_columns
                    if values[column.name] is None and not row[f"$null_{column.name}"]
                ]
                if json_nulls:
                    values["$json_nulls"] = json_nulls
                yield encode_row(values)
