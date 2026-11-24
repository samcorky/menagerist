from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator


class ImportFileStore(Protocol):
    """Where uploaded import files wait, each private to its owner."""

    async def put(
        self,
        owner_id: uuid.UUID,
        import_id: uuid.UUID,
        chunks: AsyncIterator[bytes],
        *,
        max_bytes: int,
    ) -> int:
        """Store the file and return its size in bytes.

        Raises:
            ImportFileTooLargeError: it is over `max_bytes`; nothing is kept.
        """
        ...

    async def read(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> bytes | None:
        """Return the stored file, or `None` when it is gone."""
        ...

    async def delete(self, owner_id: uuid.UUID, import_id: uuid.UUID) -> None:
        """Remove the file; nothing happens if it is gone already."""
        ...
