from typing import TYPE_CHECKING

from app.modules.transfer.domain.errors import ImportFileTooLargeError

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator


class InMemoryImportFileStore:
    """Dict-backed `ImportFileStore` for tests."""

    def __init__(self) -> None:
        self.files: dict[tuple[uuid.UUID, uuid.UUID], bytes] = {}

    async def put(
        self,
        owner_id: uuid.UUID,
        import_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> int:
        """Keep the file and return its size in bytes."""
        data = bytearray()
        async for chunk in chunks:
            data.extend(chunk)
            if len(data) > max_bytes:
                raise ImportFileTooLargeError(
                    f"The file is over the {max_bytes // (1024 * 1024)} MB limit."
                )
        self.files[owner_id, import_id] = bytes(data)
        return len(data)

    async def read(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> bytes | None:
        """Return the stored file, or `None` when it is gone."""
        return self.files.get((owner_id, import_id))

    async def delete(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> None:
        """Remove the file; nothing happens if it is gone already."""
        self.files.pop((owner_id, import_id), None)
