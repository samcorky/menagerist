import hashlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.modules.media.domain.errors import MediaFileTooLargeError
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.ports.media_storage import StoredFile

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncGenerator, AsyncIterator


class InMemoryMediaStorage:
    """Dict-backed `MediaStoragePort` for tests - no filesystem required."""

    def __init__(self) -> None:
        self._files: dict[tuple[uuid.UUID, str], bytes] = {}
        self._thumbnails: dict[tuple[uuid.UUID, str], bytes] = {}
        # When each file was last written; tests backdate entries to age them.
        self.modified_at: dict[tuple[uuid.UUID, str], datetime] = {}

    async def store(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        stream: AsyncIterator[bytes],
        *,
        max_size: int | None = None,
    ) -> tuple[int, str]:
        """Buffer the entire stream (acceptable for tests) and record it."""
        data = b""
        async for chunk in stream:
            data += chunk
            if max_size is not None and len(data) > max_size:
                raise MediaFileTooLargeError(
                    f"upload exceeds the {max_size}-byte limit"
                )
        self._files[(asset_id, status.value)] = data
        self.modified_at[(asset_id, status.value)] = datetime.now(UTC)
        return len(data), hashlib.sha256(data).hexdigest()

    def retrieve(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        """Return an async generator that yields the stored bytes."""
        return self._stream(asset_id, status)

    async def _stream(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        yield self._files.get((asset_id, status.value), b"")

    async def move(
        self,
        asset_id: uuid.UUID,
        from_status: MediaStatus,
        to_status: MediaStatus,
    ) -> None:
        """Move the bytes to the new lifecycle bucket."""
        data = self._files.pop((asset_id, from_status.value))
        self._files[(asset_id, to_status.value)] = data
        if (modified := self.modified_at.pop((asset_id, from_status.value), None)):
            self.modified_at[(asset_id, to_status.value)] = modified
        if (asset_id, from_status.value) in self._thumbnails:
            self._thumbnails[(asset_id, to_status.value)] = self._thumbnails.pop(
                (asset_id, from_status.value)
            )

    async def delete(self, asset_id: uuid.UUID, status: MediaStatus) -> None:
        """Remove the stored bytes (no-op if absent)."""
        self._files.pop((asset_id, status.value), None)
        self._thumbnails.pop((asset_id, status.value), None)
        self.modified_at.pop((asset_id, status.value), None)

    async def store_thumbnail(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        data: bytes,
    ) -> None:
        """Store pre-generated thumbnail bytes in memory."""
        self._thumbnails[(asset_id, status.value)] = data

    def retrieve_thumbnail(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        """Return an async generator that yields the thumbnail bytes."""
        return self._stream_thumbnail(asset_id, status)

    async def _stream_thumbnail(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        yield self._thumbnails.get((asset_id, status.value), b"")

    async def list_files(self, *, older_than: datetime) -> AsyncIterator[StoredFile]:
        """Yield each stored asset last written before `older_than`."""
        for (asset_id, status), _ in list(self._files.items()):
            written = self.modified_at.get((asset_id, status), datetime.now(UTC))
            if written < older_than:
                yield StoredFile(asset_id=asset_id, status=MediaStatus(status))
