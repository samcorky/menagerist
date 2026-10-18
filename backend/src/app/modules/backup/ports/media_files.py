from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.domain.backup import MediaFileRef


class MediaFiles(Protocol):
    """Original media files, independent of the media bounded context."""

    async def list_files(self) -> list[MediaFileRef]:
        """Return references from asset records, excluding thumbnails."""
        ...

    def open(self, ref: MediaFileRef) -> AsyncIterator[bytes]:
        """Stream an original, raising MediaFileMissingError if absent."""
        ...

    async def write(self, ref: MediaFileRef, stream: AsyncIterator[bytes]) -> None:
        """Write an original into its recorded status bucket."""
        ...

    async def remove(self, ref: MediaFileRef) -> None:
        """Remove a file written during an unsuccessful restore."""
        ...
