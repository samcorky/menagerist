"""A dictionary-backed `SettingValueRepository` for fast tests."""

from copy import copy
from uuid import UUID

from app.modules.settings.domain.setting import SettingScope, StoredSetting

type Address = tuple[SettingScope, UUID | None, str]


class InMemorySettingValueRepository:
    """Detached copies keyed by scope, owner and key."""

    def __init__(self, rows: dict[Address, StoredSetting] | None = None) -> None:
        self._rows = rows if rows is not None else {}

    async def get(
        self, scope: SettingScope, owner_id: UUID | None, key: str
    ) -> StoredSetting | None:
        """Return a copy of the row, if saved."""
        row = self._rows.get((scope, owner_id, key))
        return copy(row) if row is not None else None

    async def list(
        self, scope: SettingScope, owner_id: UUID | None
    ) -> dict[str, StoredSetting]:
        """Return copies of every row for one owner."""
        return {
            key: copy(row)
            for (row_scope, row_owner, key), row in self._rows.items()
            if row_scope is scope and row_owner == owner_id
        }

    async def save(self, row: StoredSetting) -> None:
        """Store a copy, replacing any row at the same address."""
        self._rows[(row.scope, row.owner_id, row.key)] = copy(row)

    async def delete(
        self, scope: SettingScope, owner_id: UUID | None, key: str
    ) -> bool:
        """Drop the row; report whether it existed."""
        return self._rows.pop((scope, owner_id, key), None) is not None
