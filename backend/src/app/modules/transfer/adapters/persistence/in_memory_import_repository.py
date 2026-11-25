from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from app.modules.transfer.domain.item_import import ImportStatus, ItemImport
    from app.shared_kernel.content_filter import ContentFilter


class InMemoryItemImportRepository:
    """Dict-backed `ItemImportRepository` for tests."""

    def __init__(self) -> None:
        self.imports: dict[uuid.UUID, ItemImport] = {}

    async def add(self, item: ItemImport) -> None:
        """Add a new import."""
        self.imports[item.id] = item

    async def save(self, item: ItemImport) -> None:
        """Persist changes to an existing import."""
        self.imports[item.id] = item

    async def delete(self, import_id: uuid.UUID) -> None:
        """Remove an import; nothing happens if there is none."""
        self.imports.pop(import_id, None)

    async def get(
        self, import_id: uuid.UUID, *, scope: ContentFilter
    ) -> ItemImport | None:
        """Return the import with `import_id` within `scope`, or `None`."""
        item = self.imports.get(import_id)
        return item if item is not None and scope.covers(item.owner_id) else None

    async def list_for_owner(self, *, scope: ContentFilter) -> list[ItemImport]:
        """Return the imports within `scope`, newest first."""
        owned = [i for i in self.imports.values() if scope.covers(i.owner_id)]
        return sorted(owned, key=lambda i: i.id, reverse=True)

    async def list_with_status(self, status: ImportStatus) -> list[ItemImport]:
        """Return everyone's imports with `status`, oldest first."""
        found = [i for i in self.imports.values() if i.status is status]
        return sorted(found, key=lambda i: (i.queued_at or i.created_at, i.id))

    async def recent_owners(self, limit: int) -> list[uuid.UUID]:
        """Return the owners of the `limit` imports started last, newest first."""
        started = [i for i in self.imports.values() if i.started_at is not None]
        started.sort(key=lambda i: (i.started_at, i.id), reverse=True)
        return [i.owner_id for i in started[:limit] if i.owner_id is not None]

    async def list_expired(self, before: datetime) -> list[ItemImport]:
        """Return everyone's imports that expired before `before`."""
        return [i for i in self.imports.values() if i.expires_at < before]
