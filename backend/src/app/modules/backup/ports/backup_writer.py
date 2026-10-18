from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.backup.domain.backup import (
        BackupManifest,
        MemberDigest,
        StoredBackup,
    )


class BackupWriter(Protocol):
    """Build and atomically publish an archive."""

    async def add(self, name: str, chunks: AsyncIterator[bytes]) -> MemberDigest:
        """Consume a member and return its uncompressed digest."""
        ...

    async def finish(self, manifest: BackupManifest) -> StoredBackup:
        """Write integrity metadata and publish the summary last."""
        ...

    async def abort(self) -> None:
        """Discard partial output."""
        ...
