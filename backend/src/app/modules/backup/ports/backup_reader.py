from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from app.modules.backup.ports.archive_member import ArchiveMember


class BackupReader(Protocol):
    """Sequential access to uncompressed archive members."""

    def members(self) -> AsyncGenerator[ArchiveMember]:
        """Yield members in archive order; consume each before advancing."""
        ...

    async def archive_digest(self) -> str:
        """Return the compressed digest computed while consuming the archive."""
        ...
