from typing import TYPE_CHECKING

from app.modules.backup.adapters.storage.in_memory_backup_reader import (
    InMemoryBackupReader,
)
from app.modules.backup.adapters.storage.in_memory_backup_writer import (
    InMemoryBackupWriter,
)
from app.modules.backup.domain.errors import BackupNotFoundError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app.modules.backup.domain.backup import BackupSummary


class InMemoryBackupStore:
    """Dictionary-backed committed archives with independent digest sidecars."""

    def __init__(self) -> None:
        self.archives: dict[UUID, bytes] = {}
        self.members: dict[UUID, dict[str, bytes]] = {}
        self.summaries: dict[UUID, BackupSummary] = {}
        self.digests: dict[UUID, str] = {}

    async def begin(self, backup_id: UUID) -> InMemoryBackupWriter:
        """Create unpublished member storage."""
        return InMemoryBackupWriter(
            backup_id, self.archives, self.members, self.summaries, self.digests
        )

    async def open(self, backup_id: UUID) -> InMemoryBackupReader:
        """Open a committed archive's members."""
        self._require(backup_id)
        return InMemoryBackupReader(self.members[backup_id])

    async def read_bytes(self, backup_id: UUID) -> AsyncIterator[bytes]:
        """Stream the compressed bytes."""
        self._require(backup_id)
        yield self.archives[backup_id]

    async def archive_digest(self, backup_id: UUID) -> str | None:
        """Return the independently stored sidecar digest."""
        self._require(backup_id)
        return self.digests.get(backup_id)

    async def list(self) -> list[BackupSummary]:
        """List only archives with a commit marker."""
        return list(self.summaries.values())

    async def delete(self, backup_id: UUID) -> None:
        """Remove the commit marker before archive data and its sidecar."""
        self._require(backup_id)
        del self.summaries[backup_id]
        self.archives.pop(backup_id, None)
        self.members.pop(backup_id, None)
        self.digests.pop(backup_id, None)

    def _require(self, backup_id: UUID) -> None:
        if backup_id not in self.summaries:
            raise BackupNotFoundError(f"Backup {backup_id} was not found.")
