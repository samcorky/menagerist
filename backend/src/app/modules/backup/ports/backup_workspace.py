from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app.modules.backup.ports.backup_reader import BackupReader


class BackupWorkspace(Protocol):
    """Private disk staging on the backup volume, isolated by opaque keys."""

    async def save(self, stream: AsyncIterator[bytes]) -> UUID:
        """Stage bytes and remove partial output on failure."""
        ...

    def read(self, key: UUID) -> AsyncIterator[bytes]:
        """Stream a staged file."""
        ...

    async def open_archive(self, key: UUID) -> BackupReader:
        """Open staged compressed bytes."""
        ...

    async def remove(self, key: UUID) -> None:
        """Discard staged bytes."""
        ...
