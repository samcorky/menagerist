"""Owner-filtered reflected database snapshots."""

from typing import TYPE_CHECKING

from sqlalchemy import JSON, MetaData, and_, false, or_, select

from app.modules.backup.adapters.persistence.database_snapshot import (
    SqlAlchemyDatabaseSnapshot,
)
from app.modules.backup.adapters.persistence.user_transfer_rows import (
    USER_TABLES,
    installation_vocabulary,
    preset_ids,
)
from app.modules.backup.domain.errors import CorruptBackupError
from app.modules.backup.ports.archive_member import ArchiveMember

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from uuid import UUID

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection
    from sqlalchemy.sql.elements import ColumnElement

    from app.shared_kernel.content_filter import ContentFilter


class SqlAlchemyUserDatabaseSnapshot(SqlAlchemyDatabaseSnapshot):
    """Stream one person's content without any account or authentication rows."""

    async def export(self, *, scope: ContentFilter) -> AsyncGenerator[ArchiveMember]:  # type: ignore[override]
        """Take a repeatable snapshot, including only referenced shared vocabulary."""
        if scope.user_id is None:
            raise CorruptBackupError("User export requires one owner.")
        async with self._session_factory() as session:
            connection = await session.connection(
                execution_options={
                    "isolation_level": "REPEATABLE READ",
                    "postgresql_readonly": True,
                }
            )
            metadata = MetaData()
            await connection.run_sync(metadata.reflect)
            tables = metadata.tables
            predicates = self._predicates(tables, scope.user_id)
            installation_refs: dict[str, set[str]] = {
                name: set() for name in ("presets", "node_types", "edge_types")
            }
            async with connection.stream(
                select(tables["example_installations"].c.entities).where(
                    predicates["example_installations"]
                )
            ) as result:
                async for records in result.scalars():
                    for name, ids in installation_vocabulary(records).items():
                        installation_refs[name].update(ids)
            for name in ("node_types", "edge_types"):
                predicates[name] = or_(
                    predicates[name], tables[name].c.id.in_(installation_refs[name])
                )
            refs = installation_refs["presets"]
            for name, column in (
                ("node_types", "attributes_schema"),
                ("edge_types", "attributes_schema"),
                ("nodes", "extra_schema"),
            ):
                async with connection.stream(
                    select(tables[name].c[column]).where(predicates[name])
                ) as result:
                    async for schema in result.scalars():
                        refs.update(preset_ids(schema))
            predicates["presets"] = tables["presets"].c.id.in_(refs)
            for name in USER_TABLES:
                yield ArchiveMember(
                    name=f"data/{name}.ndjson",
                    chunks=self._filtered_rows(
                        connection, tables[name], predicates[name]
                    ),
                )

    @staticmethod
    def _predicates(
        tables: dict[str, Table], owner_id: UUID
    ) -> dict[str, ColumnElement[bool]]:
        predicates: dict[str, ColumnElement[bool]] = {
            name: false() for name in USER_TABLES
        }
        for name in (
            "nodes",
            "edges",
            "collections",
            "media_assets",
            "example_installations",
        ):
            predicates[name] = tables[name].c.owner_id == owner_id
        nodes = select(tables["nodes"].c.id).where(predicates["nodes"])
        predicates["edges"] = and_(
            predicates["edges"],
            tables["edges"].c.source_id.in_(nodes),
            tables["edges"].c.target_id.in_(nodes),
        )
        predicates["collection_members"] = and_(
            tables["collection_members"].c.collection_id.in_(
                select(tables["collections"].c.id).where(predicates["collections"])
            ),
            tables["collection_members"].c.item_id.in_(nodes),
        )
        predicates["media_attachments"] = and_(
            tables["media_attachments"].c.asset_id.in_(
                select(tables["media_assets"].c.id).where(predicates["media_assets"])
            ),
            tables["media_attachments"].c.target_type == "node",
            tables["media_attachments"].c.target_id.in_(nodes),
        )
        for vocabulary, content in (("node_types", "nodes"), ("edge_types", "edges")):
            predicates[vocabulary] = and_(
                tables[vocabulary].c.deleted_at.is_(None),
                tables[vocabulary].c.slug.in_(
                    select(tables[content].c.type).where(predicates[content])
                ),
            )
        return predicates

    @staticmethod
    async def _filtered_rows(
        connection: AsyncConnection, table: Table, predicate: ColumnElement[bool]
    ) -> AsyncIterator[bytes]:
        from app.modules.backup.adapters.persistence.row_codec import encode_row

        json_columns = [column for column in table.c if isinstance(column.type, JSON)]
        query = select(
            table,
            *(
                column.is_(None).label(f"$null_{column.name}")
                for column in json_columns
            ),
        ).where(predicate)
        async with connection.stream(query.execution_options(yield_per=1000)) as result:
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
