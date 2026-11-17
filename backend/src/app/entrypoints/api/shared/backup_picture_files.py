"""Bridge instance backups to account picture storage."""

import hashlib
from typing import TYPE_CHECKING

from app.modules.backup.domain.backup import PictureFileRef
from app.modules.backup.domain.errors import MediaFileMissingError
from app.modules.identity.ports.avatar_image_processor import ProcessedAvatar

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from app.modules.identity.ports.avatar_storage import AvatarStorage


class BackupPictureFiles:
    """Read and write account picture files as backup members.

    Picture files are small (a few kilobytes), so each is read whole.
    """

    def __init__(self, storage: AvatarStorage) -> None:
        self._storage = storage

    async def list_files(self) -> list[PictureFileRef]:
        """Describe every stored picture file with its size and hash."""
        refs: list[PictureFileRef] = []
        for stored in await self._storage.list_files():
            data = await self._storage.read(stored.user_id, stored.version, stored.size)
            if data is None:
                continue
            refs.append(
                PictureFileRef(
                    user_id=stored.user_id,
                    version=stored.version,
                    pixels=stored.size,
                    size=len(data),
                    sha256=hashlib.sha256(data).hexdigest(),
                )
            )
        return refs

    async def exists(self, ref: PictureFileRef) -> bool:
        """Report whether the file is stored."""
        return (
            await self._storage.read(ref.user_id, ref.version, ref.pixels) is not None
        )

    async def open(self, ref: PictureFileRef) -> AsyncIterator[bytes]:
        """Stream the stored file, translating a missing one."""
        data = await self._storage.read(ref.user_id, ref.version, ref.pixels)
        if data is None:
            raise MediaFileMissingError(f"Missing picture {ref.member}")
        yield data

    async def write(self, ref: PictureFileRef, stream: AsyncIterator[bytes]) -> None:
        """Store the archived file where the account's picture is looked up."""
        data = b"".join([chunk async for chunk in stream])
        await self._storage.save(
            ref.user_id, ProcessedAvatar(version=ref.version, images={ref.pixels: data})
        )

    async def remove(self, ref: PictureFileRef) -> None:
        """Remove a file written by an unsuccessful restore."""
        await self._storage.delete(ref.user_id, ref.version, ref.pixels)
