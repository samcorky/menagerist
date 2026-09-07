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
    """Filesystem-backed media storage with sharded paths and atomic moves.

    All lifecycle buckets (staged/attached/orphaned) share one base directory
    so that `os.replace` can move files between them without crossing device
    boundaries — a cross-device rename would break atomicity.
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    def _path(self, asset_id: uuid.UUID, status: MediaStatus) -> Path:
        """Return the sharded path for `asset_id` in bucket `status`."""
        hex_id = asset_id.hex
        return self._base / status.value / hex_id[:2] / str(asset_id)

    async def store(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        stream: AsyncIterator[bytes],
        *,
        max_size: int | None = None,
    ) -> tuple[int, str]:
        """Stream `stream` to disk, computing sha256 and byte count as it flows.

        Writes to a `.tmp` sibling first, then atomically renames to the final
        path — a partial upload never appears at the canonical location.
        """
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
        """Return an async generator that streams the stored file in chunks."""
        return self._stream_file(asset_id, status)

    async def _stream_file(
        self, asset_id: uuid.UUID, status: MediaStatus
    ) -> AsyncGenerator[bytes]:
        path = self._path(asset_id, status)
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(_CHUNK_SIZE):
                yield chunk

    async def move(
        self,
        asset_id: uuid.UUID,
        from_status: MediaStatus,
        to_status: MediaStatus,
    ) -> None:
        """Atomically rename the file from one lifecycle bucket to another."""
        src = self._path(asset_id, from_status)
        dst = self._path(asset_id, to_status)
        await asyncio.to_thread(dst.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(os.replace, str(src), str(dst))

    async def delete(self, asset_id: uuid.UUID, status: MediaStatus) -> None:
        """Remove the stored file (no-op if already absent)."""
        path = self._path(asset_id, status)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(path.unlink)
