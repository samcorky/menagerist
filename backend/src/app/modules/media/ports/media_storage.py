from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncGenerator, AsyncIterator

    from app.modules.media.domain.media_asset import MediaStatus


class MediaStoragePort(Protocol):
    """Binary storage for media assets, independent of the underlying medium."""

    async def store(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        stream: AsyncIterator[bytes],
        *,
        max_size: int | None = None,
    ) -> tuple[int, str]:
        """Write `stream` to storage under `asset_id`/`status`.

        Returns `(size_bytes, sha256_hex)`. Raises `MediaFileTooLargeError`
        if `max_size` is given and the stream exceeds it.
        """
        ...

    def retrieve(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
    ) -> AsyncGenerator[bytes]:
        """Return an async generator that streams the asset's bytes."""
        ...

    async def move(
        self,
        asset_id: uuid.UUID,
        from_status: MediaStatus,
        to_status: MediaStatus,
    ) -> None:
        """Atomically move an asset between lifecycle buckets."""
        ...

    async def delete(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
    ) -> None:
        """Hard-delete the stored file."""
        ...
