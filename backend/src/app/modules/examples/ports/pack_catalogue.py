from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from app.modules.examples.domain.pack import ExamplePack, PackSummary


class PackCatalogue(Protocol):
    """The packs this server ships."""

    async def list_packs(self) -> list[PackSummary]:
        """Return every shipped pack's summary, in catalogue order."""
        ...

    async def get(self, pack_id: str) -> ExamplePack | None:
        """Return the pack with `pack_id`, or `None` if there is no such pack."""
        ...
