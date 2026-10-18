from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime
    from uuid import UUID

    from app.modules.backup.domain.backup import BackupSummary
    from app.modules.backup.ports.backup_reader import BackupReader
    from app.modules.backup.ports.backup_writer import BackupWriter


class BackupStore(Protocol):
    """Committed archives and their integrity sidecars."""

    async def begin(self, backup_id: UUID) -> BackupWriter:
        """Prepare writable staging storage for a new archive."""
        ...

    async def open(self, backup_id: UUID) -> BackupReader:
        """Open a committed archive, raising BackupNotFoundError if absent."""
        ...

    def read_bytes(self, backup_id: UUID) -> AsyncIterator[bytes]:
        """Stream the compressed archive for download and hashing."""
        ...

    async def archive_digest(self, backup_id: UUID) -> str | None:
        """Return the sidecar digest, or None if it is absent."""
        ...

    async def delete(self, backup_id: UUID) -> None:
        """Delete summary, archive and sidecar in that order."""
        ...

    async def unreadable(self) -> list[str]:
        """Report unreadable summary names without deleting their archives."""
        ...

    async def cleanup_orphans(self, *, before: datetime, dry_run: bool) -> list[str]:
        """Remove uncommitted archives and staging files older than before."""
        ...

    async def list(self) -> list[BackupSummary]:
        """Return summaries for committed archives only."""
        ...
