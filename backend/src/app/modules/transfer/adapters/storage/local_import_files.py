import asyncio
import os
from contextlib import suppress
from typing import TYPE_CHECKING

import aiofiles
import structlog

from app.modules.transfer.domain.errors import ImportFileTooLargeError
from app.platform.config.media import get_media_settings

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator
    from pathlib import Path

logger = structlog.get_logger()


class LocalImportFileStore:
    """`ImportFileStore` on disk, at `<base>/<owner>/<import>.csv`.

    A file is written beside its final name and moved into place once complete,
    so a half-written upload is never read.
    """

    def __init__(self, base_path: Path) -> None:
        self._base = base_path

    def _path(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> Path:
        return self._base / str(owner_id) / f"{import_id}.csv"

    async def put(
        self,
        owner_id: uuid.UUID,
        import_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> int:
        """Stream the file to disk and return its size in bytes."""
        path = self._path(owner_id, import_id)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        partial = path.with_suffix(".part")
        size = 0
        try:
            async with aiofiles.open(partial, "wb") as file:
                async for chunk in chunks:
                    size += len(chunk)
                    if size > max_bytes:
                        raise ImportFileTooLargeError(
                            f"The file is over the {max_bytes // (1024 * 1024)} MB "
                            + "limit."
                        )
                    await file.write(chunk)
            await asyncio.to_thread(os.replace, partial, path)
        except BaseException:
            with suppress(FileNotFoundError):
                await asyncio.to_thread(partial.unlink)
            raise
        logger.debug("stored import file", import_id=import_id, size=size)
        return size

    async def read(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> bytes | None:
        """Return the stored file, or `None` when it is gone."""
        try:
            async with aiofiles.open(self._path(owner_id, import_id), "rb") as file:
                return await file.read()
        except FileNotFoundError:
            return None

    async def delete(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> None:
        """Remove the file; nothing happens if it is gone already."""
        with suppress(FileNotFoundError):
            await asyncio.to_thread(self._path(owner_id, import_id).unlink)


def import_file_store() -> LocalImportFileStore:
    """Uploaded import files, under the media directory beside what they become."""
    return LocalImportFileStore(get_media_settings().storage_path / "imports")
