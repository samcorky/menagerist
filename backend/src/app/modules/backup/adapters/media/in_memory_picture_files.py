import hashlib
from typing import TYPE_CHECKING

from app.modules.backup.domain.backup import PictureFileRef
from app.modules.backup.domain.errors import MediaFileMissingError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID


class InMemoryPictureFiles:
    """Picture file bytes keyed by account, version and size, for tests."""

    def __init__(self) -> None:
        self.files: dict[tuple[UUID, str, int], bytes] = {}

    async def list_files(self) -> list[PictureFileRef]:
        """Describe every kept file."""
        return [
            PictureFileRef(
                user_id=user_id,
                version=version,
                pixels=pixels,
                size=len(data),
                sha256=hashlib.sha256(data).hexdigest(),
            )
            for (user_id, version, pixels), data in self.files.items()
        ]

    async def exists(self, ref: PictureFileRef) -> bool:
        """Report whether the file is kept."""
        return (ref.user_id, ref.version, ref.pixels) in self.files

    async def open(self, ref: PictureFileRef) -> AsyncIterator[bytes]:
        """Stream the file or report its absence."""
        key = (ref.user_id, ref.version, ref.pixels)
        if key not in self.files:
            raise MediaFileMissingError(f"Picture {ref.member} is missing.")
        yield self.files[key]

    async def write(self, ref: PictureFileRef, stream: AsyncIterator[bytes]) -> None:
        """Keep the streamed bytes."""
        self.files[ref.user_id, ref.version, ref.pixels] = b"".join(
            [chunk async for chunk in stream]
        )

    async def remove(self, ref: PictureFileRef) -> None:
        """Forget the file."""
        self.files.pop((ref.user_id, ref.version, ref.pixels), None)
