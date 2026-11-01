from typing import TYPE_CHECKING

from app.modules.backup.domain.errors import MediaFileMissingError

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

    from app.modules.backup.domain.backup import MediaFileRef


class InMemoryMediaFiles:
    """Original file bytes keyed by asset id and lifecycle bucket."""

    def __init__(self) -> None:
        self.refs: dict[UUID, MediaFileRef] = {}
        self.files: dict[tuple[UUID, str], bytes] = {}

    async def list_files(self) -> list[MediaFileRef]:
        """Return asset records, including those whose bytes are missing."""
        return list(self.refs.values())

    async def open(self, ref: MediaFileRef) -> AsyncIterator[bytes]:
        """Stream an original or report its absence."""
        key = (ref.asset_id, ref.status)
        if key not in self.files:
            raise MediaFileMissingError(f"Media file {ref.asset_id} is missing.")
        yield self.files[key]

    async def write(self, ref: MediaFileRef, stream: AsyncIterator[bytes]) -> None:
        """Buffer bytes before publishing them in their status bucket."""
        data = b"".join([chunk async for chunk in stream])
        self.files[(ref.asset_id, ref.status)] = data
        self.refs[ref.asset_id] = ref

    async def remove(self, ref: MediaFileRef) -> None:
        """Remove bytes without deleting the asset record."""
        self.files.pop((ref.asset_id, ref.status), None)
