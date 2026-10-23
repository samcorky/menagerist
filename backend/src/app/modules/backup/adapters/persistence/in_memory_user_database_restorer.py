from copy import deepcopy
from typing import TYPE_CHECKING

from app.modules.backup.adapters.persistence.in_memory_user_import_validator import (
    InMemoryUserImportValidator,
)
from app.modules.backup.adapters.persistence.user_database_restorer import (
    _validate_references,
)
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
    from uuid import UUID

    from app.modules.backup.ports.archive_member import ArchiveMember
    from app.modules.backup.ports.user_import_validator import UserImportValidator


class InMemoryUserDatabaseRestorer:
    """First-class transactional user import with shared-vocabulary matching."""

    def __init__(
        self,
        revision: str,
        tables: dict[str, list[dict[str, object]]] | None = None,
        *,
        validator: UserImportValidator | None = None,
    ) -> None:
        self.revision = revision
        self.tables = tables if tables is not None else {}
        self._validator = validator or InMemoryUserImportValidator()

    async def schema_revision(self) -> str:
        """Return the configured destination revision."""
        return self.revision

    async def import_user(
        self, members: AsyncIterator[ArchiveMember], *, new_owner_id: UUID
    ) -> None:
        """Publish staged rows only after the entire member stream succeeds."""
        target = deepcopy(self.tables)
        if any(
            str(row.get("owner_id")) == str(new_owner_id)
            for name in OWNED_TABLES
            for row in target.get(name, [])
        ):
            raise RestoreTargetNotEmptyError(
                "Import requires an account without existing content."
            )
        imported: dict[str, set[str]] = {name: set() for name in USER_TABLES}
        remap: dict[str, str] = {}
        seen: set[str] = set()
        skipped: dict[str, set[str]] = {n: set() for n in SOFT_DELETABLE}
        async for member in members:
            name = import_table_name(member.name, seen)
            rows = target.setdefault(name, [])
            async for raw in read_rows(member.chunks):
                if skip_row(name, raw, skipped):
                    continue
                row = prepare_row(name, raw, new_owner_id, remap)
                await self._validator.validate(name, row)
                _validate_references(name, row, imported)
                existing = (
                    next(
                        (
                            item
                            for item in rows
                            if str(item.get("id")) == str(row.get("id"))
                        ),
                        None,
                    )
                    if "id" in row
                    else None
                )
                if name in VOCABULARY and _reuse_vocabulary(
                    name, row, rows, existing, remap
                ):
                    imported[name].add(str(row["id"]))
                    continue
                if existing is not None:
                    raise ImportCollisionError("Imported identifier already exists.")
                rows.append(row)
                _record_identifier(name, row, imported)
        if seen != set(USER_TABLES):
            raise CorruptBackupError("User archive is missing content tables.")
        self.tables.clear()
        self.tables.update(target)


def _reuse_vocabulary(
    name: str,
    row: dict[str, object],
    rows: list[dict[str, object]],
    existing: dict[str, object] | None,
    remap: dict[str, str],
) -> bool:
    if row.get("deleted_at") is not None and existing is None:
        return False
    candidates = [
        item
        for item in rows
        if (
            (name != "presets" and item.get("slug") == row.get("slug"))
            or (
                name == "presets"
                and item.get("kind") == row.get("kind")
                and item.get("label") == row.get("label")
            )
        )
        and item.get("deleted_at") is None
    ]
    if existing is not None and (
        not compatible(name, row, existing)
        or (name != "presets" and existing.get("slug") != row.get("slug"))
    ):
        raise ImportCollisionError("Vocabulary identifier conflict.")
    matched = existing or next(
        (item for item in candidates if compatible(name, row, item)), None
    )
    if matched:
        remap[f"{name}:{row['id']}"] = str(matched["id"])
        return True
    if candidates and name != "presets":
        raise ImportCollisionError("Incompatible type slug.")
    return False


def _record_identifier(
    name: str, row: dict[str, object], imported: dict[str, set[str]]
) -> None:
    if "id" in row:
        imported[name].add(str(row["id"]))
