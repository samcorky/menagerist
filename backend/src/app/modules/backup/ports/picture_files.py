from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.domain.backup import PictureFileRef


class PictureFiles(Protocol):
    """Account picture files, independent of the identity bounded context."""

    async def list_files(self) -> list[PictureFileRef]:
        """Return every stored picture file with its size and hash."""
        ...

    async def exists(self, ref: PictureFileRef) -> bool:
        """Report whether the file is present."""
        ...

    def open(self, ref: PictureFileRef) -> AsyncIterator[bytes]:
        """Stream the file, raising MediaFileMissingError if absent."""
        ...

    async def write(self, ref: PictureFileRef, stream: AsyncIterator[bytes]) -> None:
        """Write the file where the account's picture is looked up."""
        ...

    async def remove(self, ref: PictureFileRef) -> None:
        """Remove a file written during an unsuccessful restore."""
        ...
