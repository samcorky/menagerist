import asyncio
import hashlib
import os
import uuid
from contextlib import suppress
from typing import TYPE_CHECKING

import aiofiles
import structlog

from app.modules.media.domain.errors import MediaFileTooLargeError
from app.modules.media.domain.media_asset import MediaStatus
from app.modules.media.ports.media_storage import StoredFile

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, AsyncIterator
    from datetime import datetime
    from pathlib import Path

logger = structlog.get_logger()

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
        logger.debug("storing media file", asset_id=asset_id, status=status.value)
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
        logger.debug("retrieving media file", asset_id=asset_id, status=status.value)
        return self._stream_file_at(self._path(asset_id, status))

    async def move(
        self,
        asset_id: uuid.UUID,
        from_status: MediaStatus,
        to_status: MediaStatus,
    ) -> None:
        """Atomically rename file and optional thumbnail between buckets."""
        logger.debug(
            "moving media file",
            asset_id=asset_id,
            from_status=from_status.value,
            to_status=to_status.value,
        )
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
        logger.debug("deleting media file", asset_id=asset_id, status=status.value)
        path = self._path(asset_id, status)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(path.unlink)
        thumb = self._thumb_path(asset_id, status)
        with suppress(FileNotFoundError):
            await asyncio.to_thread(thumb.unlink)
        # An interrupted upload leaves its half-written file behind.
        with suppress(FileNotFoundError):
            await asyncio.to_thread(path.with_suffix(".tmp").unlink)

    async def store_thumbnail(
        self,
        asset_id: uuid.UUID,
        status: MediaStatus,
        data: bytes,
    ) -> None:
        """Write thumbnail bytes atomically alongside the original file."""
        logger.debug(
            "storing thumbnail",
            asset_id=asset_id,
            status=status.value,
            size_bytes=len(data),
        )
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
        logger.debug("retrieving thumbnail", asset_id=asset_id, status=status.value)
        return self._stream_file_at(self._thumb_path(asset_id, status))

    async def _stream_file_at(self, path: Path) -> AsyncGenerator[bytes]:
        async with aiofiles.open(path, "rb") as f:
            while chunk := await f.read(_CHUNK_SIZE):
                yield chunk

    async def list_files(self, *, older_than: datetime) -> AsyncIterator[StoredFile]:
        """Yield each stored asset last modified before `older_than`, once."""
        cutoff = older_than.timestamp()
        for status in MediaStatus:
            bucket = self._base / status.value
            shards = await asyncio.to_thread(_subdirectories, bucket)
            for shard in shards:
                for asset_id in await asyncio.to_thread(_old_asset_ids, shard, cutoff):
                    yield StoredFile(asset_id=asset_id, status=status)


def _subdirectories(folder: Path) -> list[Path]:
    """Return the directories inside `folder`, or none if it does not exist."""
    try:
        return sorted(entry for entry in folder.iterdir() if entry.is_dir())
    except FileNotFoundError:
        return []


def _old_asset_ids(shard: Path, cutoff: float) -> list[uuid.UUID]:
    """Return ids of assets in `shard` with a file last modified before `cutoff`.

    A file counts for its asset whether it is the original, the thumbnail or a
    half-written upload; names that are not an asset id are ignored.
    """
    found: dict[uuid.UUID, None] = {}
    for entry in shard.iterdir():
        try:
            asset_id = uuid.UUID(entry.name.partition(".")[0])
        except ValueError:
            continue
        if entry.is_file() and entry.stat().st_mtime < cutoff:
            found[asset_id] = None
    return list(found)
