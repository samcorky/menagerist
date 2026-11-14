from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.catalogue.domain.entry import CatalogueEntry


class EntryCatalogue(Protocol):
    """The entries this server ships."""

    async def list_entries(self) -> list[CatalogueEntry]:
        """Return every entry, in a stable order."""
        ...

    async def get(self, entry_id: str) -> CatalogueEntry | None:
        """Return the entry with `entry_id`, or `None`."""
        ...
