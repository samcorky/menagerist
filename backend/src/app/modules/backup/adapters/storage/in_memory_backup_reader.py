from typing import TYPE_CHECKING

from app.modules.backup.ports.archive_member import ArchiveMember

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator


async def byte_chunks(data: bytes) -> AsyncIterator[bytes]:
    """Yield buffered test bytes as a stream."""
    yield data


class InMemoryBackupReader:
    """Ordered member streams backed by buffered bytes."""

    def __init__(self, members: dict[str, bytes]) -> None:
        self._members = members

    async def members(self) -> AsyncGenerator[ArchiveMember]:
        """Yield members in insertion order."""
        for name, data in self._members.items():
            yield ArchiveMember(name=name, chunks=byte_chunks(data))
