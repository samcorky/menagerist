from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.catalogue.application.permissions import CataloguePermission
from app.modules.catalogue.domain.errors import CatalogueEntryNotFoundError
from app.modules.catalogue.ports.entry_catalogue import EntryCatalogue  # noqa: TC001
from app.modules.transfer.domain.entity_kind import EntityKind
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class InstallCatalogueEntryCommand:
    """Request to install one shipped entry for the signed-in person."""

    entry_id: str


@dataclass(kw_only=True, frozen=True, eq=False)
class InstallOutcome:
    """What an install created, and what the person already had."""

    entry_id: str
    presets_created: int = 0
    presets_skipped: int = 0
    item_types_created: int = 0
    item_types_skipped: int = 0
    relationship_types_created: int = 0
    relationship_types_skipped: int = 0


class InstallCatalogueEntry(UseCase[InstallCatalogueEntryCommand, InstallOutcome]):
    """Install an entry as ordinary, owned presets or types.

    Installing is idempotent: an identical preset or a taken slug is skipped. A
    failure part-way leaves what was made in place, and installing again finishes it.
    Nothing is recorded, so nothing it makes is labelled as an example.

    Raises:
        CatalogueEntryNotFoundError: the catalogue has no such entry.
    """

    access: ClassVar[Access] = Requires(CataloguePermission.ENTRY_INSTALL)

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
        self, request: InstallCatalogueEntryCommand, actor: Actor
    ) -> InstallOutcome:
        """Create what the person does not already have."""
        entry = await self._catalogue.get(request.entry_id)
        if entry is None:
            raise CatalogueEntryNotFoundError(
                f"Catalogue entry '{request.entry_id}' not found"
            )
        outcomes = await self._presets.ensure(entry.presets)
        created = sum(1 for o in outcomes if o.created)
        item_created = 0
        for spec in entry.item_types:
            if not await self._graph.slug_taken(EntityKind.ITEM_TYPE, spec.slug):
                await self._graph.create_item_type(spec, {})
                item_created += 1
        rel_created = 0
        for rel in entry.relationship_types:
            if not await self._graph.slug_taken(EntityKind.RELATIONSHIP_TYPE, rel.slug):
                await self._graph.create_relationship_type(rel, {})
                rel_created += 1
        result = InstallOutcome(
            entry_id=entry.id,
            presets_created=created,
            presets_skipped=len(outcomes) - created,
            item_types_created=item_created,
            item_types_skipped=len(entry.item_types) - item_created,
            relationship_types_created=rel_created,
            relationship_types_skipped=len(entry.relationship_types) - rel_created,
        )
        logger.info("catalogue entry installed", entry=entry.id)
        return result
