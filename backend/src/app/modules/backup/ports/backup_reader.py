from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.ports.archive_member import ArchiveMember


class BackupReader(Protocol):
    """Sequential access to uncompressed archive members."""

    def members(self) -> AsyncIterator[ArchiveMember]:
        """Yield members in archive order; consume each before advancing."""
        ...
