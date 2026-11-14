from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.catalogue.application.permissions import CataloguePermission
from app.modules.catalogue.domain.entry import CatalogueEntry
from app.modules.catalogue.ports.entry_catalogue import EntryCatalogue  # noqa: TC001
from app.modules.transfer.domain.entity_kind import EntityKind
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListCatalogueEntriesQuery:
    """Request to list the shipped entries with what the person already has."""


@dataclass(kw_only=True, frozen=True, eq=False)
class EntryStatus:
    """An entry, and how much of it the person already has."""

    entry: CatalogueEntry
    present: int
    total: int

    @property
    def installed(self) -> bool:
        """Whether everything the entry holds is already there."""
        return self.present == self.total


async def count_present(
    entry: CatalogueEntry, presets: PresetTarget, graph: GraphTarget
) -> EntryStatus:
    """Count how many of the entry's presets or types the person already has."""
    present = sum(await presets.existing(entry.presets))
    for spec in entry.item_types:
        present += await graph.slug_taken(EntityKind.ITEM_TYPE, spec.slug)
    for rel in entry.relationship_types:
        present += await graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, rel.slug)
    total = len(entry.presets) + len(entry.item_types) + len(entry.relationship_types)
    return EntryStatus(entry=entry, present=present, total=total)


class ListCatalogueEntries(UseCase[ListCatalogueEntriesQuery, list[EntryStatus]]):
    """List every entry, with whether the person has already installed it."""

    access: ClassVar[Access] = Requires(CataloguePermission.ENTRY_READ)

    def __init__(
        self,
        guard: AccessGuard,
        catalogue: EntryCatalogue,
        presets: PresetTarget,
        graph: GraphTarget,
    ) -> None:
        """Initialise with the access guard, the catalogue and the two targets."""
        self._guard = guard
        self._catalogue = catalogue
        self._presets = presets
        self._graph = graph

    async def _handle(
        self, request: ListCatalogueEntriesQuery, actor: Actor
    ) -> list[EntryStatus]:
        """Return one status per entry; nothing is created."""
        return [
            await count_present(entry, self._presets, self._graph)
            for entry in await self._catalogue.list_entries()
        ]
