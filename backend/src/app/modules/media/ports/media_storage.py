import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from app.modules.media.domain.media_asset import MediaStatus

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from datetime import datetime


@dataclass(frozen=True, slots=True, kw_only=True)
class StoredFile:
    """One asset's file as found in storage, whether or not a row still exists."""

    asset_id: uuid.UUID
    status: MediaStatus


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

    async def store_thumbnail(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        data: bytes,
    ) -> None:
        """Write pre-generated thumbnail bytes alongside the original file."""
        ...

    def retrieve_thumbnail(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
    ) -> AsyncGenerator[bytes]:
        """Return an async generator that streams the thumbnail bytes."""
        ...

    def list_files(self, *, older_than: datetime) -> AsyncIterator[StoredFile]:
        """Yield each stored asset last modified before `older_than`, once.

        Thumbnails and half-written uploads belong to their asset and do not
        appear separately. Files that are not named for an asset are ignored.
        """
        ...
