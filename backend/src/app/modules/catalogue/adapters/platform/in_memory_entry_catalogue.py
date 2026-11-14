from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from app.modules.catalogue.domain.entry import CatalogueEntry


class InMemoryEntryCatalogue:
    """A catalogue built in code, for tests."""

    def __init__(self, entries: Sequence[CatalogueEntry]) -> None:
        self._entries = list(entries)

    async def list_entries(self) -> list[CatalogueEntry]:
        """Return the entries in the order given."""
        return list(self._entries)

    async def get(self, entry_id: str) -> CatalogueEntry | None:
        """Return the entry with `entry_id`, or `None`."""
        return next((e for e in self._entries if e.id == entry_id), None)
