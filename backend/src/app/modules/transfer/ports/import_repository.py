from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.transfer.domain.item_import import ImportStatus, ItemImport
    from app.shared_kernel.content_filter import ContentFilter


class ItemImportRepository(Protocol):
    """Uploaded import files and what became of them."""

    async def add(self, item: ItemImport) -> None:
        """Add a new import."""
        ...

    async def save(self, item: ItemImport) -> None:
        """Persist changes to an existing import."""
        ...

    async def delete(self, import_id: uuid.UUID) -> None:
        """Remove an import; nothing happens if there is none."""
        ...

    async def get(
        self, import_id: uuid.UUID, *, scope: ContentFilter
    ) -> ItemImport | None:
        """Return the import with `import_id` within `scope`, or `None`."""
        ...

    async def list_for_owner(self, *, scope: ContentFilter) -> list[ItemImport]:
        """Return the imports within `scope`, newest first."""
        ...

    async def list_with_status(self, status: ImportStatus) -> list[ItemImport]:
        """Return everyone's imports with `status`, oldest first."""
        ...

    async def recent_owners(self, limit: int) -> list[uuid.UUID]:
        """Return the owners of the `limit` imports started last, newest first."""
        ...

    async def list_expired(self, before: datetime) -> list[ItemImport]:
        """Return everyone's imports that expired before `before`."""
        ...
