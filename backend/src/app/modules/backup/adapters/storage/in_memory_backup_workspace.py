from typing import TYPE_CHECKING
from uuid import UUID, uuid7

from app.modules.backup.adapters.storage.local_backup_reader import LocalBackupReader

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class InMemoryBackupWorkspace:
    """Private staging dictionary for application tests."""

    def __init__(self) -> None:
        self.files: dict[UUID, bytes] = {}

    async def save(self, stream: AsyncIterator[bytes]) -> UUID:
        """Consume a stream before publishing its staging key."""
        data = b"".join([chunk async for chunk in stream])
        key = uuid7()
        self.files[key] = data
        return key

    async def read(self, key: UUID) -> AsyncIterator[bytes]:
        """Read staged bytes."""
        yield self.files[key]

    async def open_archive(self, key: UUID) -> LocalBackupReader:
        """Open a staged archive."""
        return LocalBackupReader(self.files[key])

    async def remove(self, key: UUID) -> None:
        """Discard staging bytes."""
        self.files.pop(key, None)
