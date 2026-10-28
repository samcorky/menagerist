"""Storage for values saved by administrators and people."""

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from uuid import UUID

    from app.modules.settings.domain.setting import SettingScope, StoredSetting


class SettingValueRepository(Protocol):
    """Saved rows, one per scope, owner and key."""

    async def get(
        self, scope: SettingScope, owner_id: UUID | None, key: str
    ) -> StoredSetting | None:
        """Return the row, or nothing when no value has been saved."""
        ...

    async def list(
        self, scope: SettingScope, owner_id: UUID | None
    ) -> dict[str, StoredSetting]:
        """Return every saved row for one owner, by key."""
        ...

    async def save(self, row: StoredSetting) -> None:
        """Insert the row, or replace the saved value for its scope, owner and key."""
        ...

    async def delete(
        self, scope: SettingScope, owner_id: UUID | None, key: str
    ) -> bool:
        """Remove a saved value; report whether one existed."""
        ...
