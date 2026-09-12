import asyncio
import hashlib
import os
from contextlib import suppress
from typing import TYPE_CHECKING

import aiofiles

from app.modules.media.domain.errors import MediaFileTooLargeError

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncGenerator, AsyncIterator
    from pathlib import Path

    from app.modules.media.domain.media_asset import MediaStatus

_CHUNK_SIZE = 64 * 1024


class LocalFilesystemMediaStorage:
    """Filesystem-backed media storage with sharded paths and atomic moves."""

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    @staticmethod
    def _shard(asset_id: uuid.UUID) -> str:
        """Return filesystem shard for asset_id."""
        return hashlib.sha256(asset_id.bytes).hexdigest()[:2]

    def _path(self, asset_id: uuid.UUID, status: MediaStatus) -> Path:
        """Return sharded path for asset_id in bucket status."""
        return self._base / status.value / self._shard(asset_id) / str(asset_id)

    def _thumb_path(self, asset_id: uuid.UUID, status: MediaStatus) -> Path:
        """Return thumbnail sibling path for asset_id."""
        return self._path(asset_id, status).with_suffix(".thumb")

    async def store(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        stream: AsyncIterator[bytes],
        *,
        max_size: int | None = None,
    ) -> tuple[int, str]:
        """Stream data to disk, computing sha256 and byte count."""
        path = self._path(asset_id, status)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        hasher = hashlib.sha256()
        total = 0
        try:
            async with aiofiles.open(tmp, "wb") as f:
                async for chunk in stream:
                    total += len(chunk)
                    if max_size is not None and total > max_size:
                        raise MediaFileTooLargeError(
                            f"upload exceeds the {max_size}-byte limit"
                        )
                    hasher.update(chunk)
                    await f.write(chunk)
            await asyncio.to_thread(os.replace, str(tmp), str(path))
        except Exception:
            with suppress(FileNotFoundError):
                await asyncio.to_thread(tmp.unlink)
            raise
        return total, hasher.hexdigest()

    def retrieve(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        """Return async generator streaming the stored file."""
        return self._stream_file_at(self._path(asset_id, status))

    async def move(
        self,
        asset_id: uuid.UUID,
        from_status: MediaStatus,
        to_status: MediaStatus,
    ) -> None:
        """Atomically rename file and optional thumbnail between buckets."""
        src = self._path(asset_id, from_status)
        dst = self._path(asset_id, to_status)
        await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(os.replace, str(src), str(dst))
        src_thumb = self._thumb_path(asset_id, from_status)
        dst_thumb = self._thumb_path(asset_id, to_status)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(os.replace, str(src_thumb), str(dst_thumb))

    async def delete(self, asset_id: uuid.UUID, status: MediaStatus) -> None:
        """Remove stored file and its thumbnail sibling."""
        path = self._path(asset_id, status)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(path.unlink)
        thumb = self._thumb_path(asset_id, status)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(thumb.unlink)

    async def store_thumbnail(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        data: bytes,
    ) -> None:
        """Write thumbnail bytes atomically alongside the original file."""
        path = self._thumb_path(asset_id, status)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        tmp = path.parent / (path.name + ".tmp")
        try:
            async with aiofiles.open(tmp, "wb") as f:
                await f.write(data)
            await asyncio.to_thread(os.replace, str(tmp), str(path))
        except Exception:
            with suppress(FileNotFoundError):
                await asyncio.to_thread(tmp.unlink)
            raise

    def retrieve_thumbnail(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        """Return an async generator that streams the thumbnail bytes."""
        return self._stream_file_at(self._thumb_path(asset_id, status))

    async def _stream_file_at(self, path: Path) -> AsyncGenerator[bytes]:
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(_CHUNK_SIZE):
                yield chunk
