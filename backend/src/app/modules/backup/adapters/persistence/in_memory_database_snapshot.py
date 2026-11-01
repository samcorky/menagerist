from typing import TYPE_CHECKING

from app.modules.backup.adapters.storage.in_memory_backup_reader import (
    InMemoryBackupReader,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.modules.backup.ports.archive_member import ArchiveMember


class InMemoryDatabaseSnapshot:
    """Fixed revision and ordered logical table exports."""

    def __init__(self, revision: str, tables: dict[str, bytes]) -> None:
        self._revision = revision
        self._tables = tables

    async def schema_revision(self) -> str:
        """Return the configured source revision."""
        return self._revision

    def export(self) -> AsyncGenerator[ArchiveMember]:
        """Stream the supplied table bytes in insertion order."""
        return InMemoryBackupReader(self._tables).members()
