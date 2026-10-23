"""Atomic owner-stamped imports over reflected tables."""

from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import insert, select, text
from sqlalchemy.exc import IntegrityError

from app.modules.backup.adapters.persistence.database_restorer import (
    SqlAlchemyDatabaseRestorer,
)
from app.modules.backup.adapters.persistence.row_codec import decode_row
from app.modules.backup.adapters.persistence.user_transfer_rows import (
    OWNED_TABLES,
    SOFT_DELETABLE,
    USER_TABLES,
    VOCABULARY,
    compatible,
    import_table_name,
    prepare_row,
    read_rows,
    skip_row,
)
from app.modules.backup.domain.errors import (
    CorruptBackupError,
    ImportCollisionError,
    RestoreTargetNotEmptyError,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy import Table
    from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker

    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.modules.backup.ports.user_import_validator import UserImportValidator


class SqlAlchemyUserDatabaseRestorer(SqlAlchemyDatabaseRestorer):
    """Import without changing accounts, permissions or existing owners' rows."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        validator: UserImportValidator,
    ) -> None:
        super().__init__(session_factory)
        self._validator = validator

    async def import_user(
        self, members: AsyncIterator[ArchiveMember], *, new_owner_id: UUID
    ) -> None:
        """Hold content-table locks through validation, inserts and media writes."""
        try:
            async with self._session_factory() as session, session.begin():
                connection = await session.connection()
                tables = {table.name: table for table in await self._tables(connection)}
                names = ", ".join(
                    connection.dialect.identifier_preparer.format_table(tables[name])
                    for name in USER_TABLES
                )
                await connection.execute(text(f"LOCK TABLE {names} IN EXCLUSIVE MODE"))
                await self._assert_empty(connection, tables, new_owner_id)
                remap: dict[str, str] = {}
                imported: dict[str, set[str]] = {name: set() for name in USER_TABLES}
                seen: set[str] = set()
                skipped: dict[str, set[str]] = {n: set() for n in SOFT_DELETABLE}
                async for member in members:
                    name = import_table_name(member.name, seen)
                    async for raw in read_rows(member.chunks):
                        if skip_row(name, raw, skipped):
                            continue
                        row = prepare_row(name, raw, new_owner_id, remap)
                        await self._validator.validate(name, row)
                        _validate_references(name, row, imported)
                        await self._insert_row(connection, tables[name], row, remap)
                        if "id" in row:
                            imported[name].add(str(row["id"]))
                if seen != set(USER_TABLES):
                    raise CorruptBackupError("User archive is missing content tables.")
        except IntegrityError as exc:
            raise ImportCollisionError(
                "An imported identifier already exists or a reference is invalid."
            ) from exc

    @staticmethod
    async def _assert_empty(
        connection: AsyncConnection, tables: dict[str, Table], owner_id: UUID
    ) -> None:
        for name in OWNED_TABLES:
            query = select(tables[name]).where(tables[name].c.owner_id == owner_id)
            if await connection.scalar(select(query.exists())):
                raise RestoreTargetNotEmptyError(
                    "Import requires an account without existing content."
                )

    async def _insert_row(
        self,
        connection: AsyncConnection,
        table: Table,
        row: dict[str, object],
        remap: dict[str, str],
    ) -> None:
        if table.name in VOCABULARY:
            existing = await self._vocabulary(connection, table, row)
            if existing is not None:
                remap[f"{table.name}:{row['id']}"] = str(existing["id"])
                return
        decoded = decode_row(row, table)
        await connection.execute(insert(table).values(**decoded))

    @staticmethod
    async def _vocabulary(
        connection: AsyncConnection, table: Table, row: dict[str, object]
    ) -> dict[str, object] | None:
        name = table.name
        identifier = UUID(str(row["id"]))
        by_id = (
            (await connection.execute(select(table).where(table.c.id == identifier)))
            .mappings()
            .first()
        )
        if name == "presets":
            query = select(table).where(
                table.c.kind == row["kind"],
                table.c.label == row["label"],
                table.c.deleted_at.is_(None),
            )
        else:
            query = select(table).where(
                table.c.slug == row["slug"], table.c.deleted_at.is_(None)
            )
        candidates = (await connection.execute(query)).mappings().all()
        if by_id is not None:
            if not compatible(name, row, dict(by_id)) or (
                name != "presets" and row["slug"] != by_id["slug"]
            ):
                raise ImportCollisionError(
                    "A vocabulary identifier conflicts with existing content."
                )
            return dict(by_id)
        if row.get("deleted_at") is not None:
            return None
        for candidate in candidates:
            if compatible(name, row, dict(candidate)):
                return dict(candidate)
        if candidates and name != "presets":
            raise ImportCollisionError(
                "An existing type slug has an incompatible schema."
            )
        return None


def _validate_references(
    name: str, row: dict[str, object], imported: dict[str, set[str]]
) -> None:
    """Reject links from the incoming content into another account's data."""
    references = {
        "edges": (("source_id", "nodes"), ("target_id", "nodes")),
        "collection_members": (("collection_id", "collections"), ("item_id", "nodes")),
        "media_attachments": (("asset_id", "media_assets"), ("target_id", "nodes")),
    }
    for key, target in references.get(name, ()):
        if str(row.get(key)) not in imported[target]:
            raise CorruptBackupError(
                "User archive references content outside the import."
            )
    if name == "media_attachments" and row.get("target_type") != "node":
        raise CorruptBackupError("User archive has an unsupported attachment target.")
