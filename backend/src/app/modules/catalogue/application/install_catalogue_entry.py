from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.catalogue.application.permissions import CataloguePermission
from app.modules.catalogue.domain.errors import CatalogueEntryNotFoundError
from app.modules.catalogue.ports.entry_catalogue import EntryCatalogue  # noqa: TC001
from app.modules.transfer.application.pipeline import apply_bundle, plan_bundle
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import ClashPolicy
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

    Installing is idempotent: it plans the entry with `plan_bundle`, which skips
    an identical preset or a taken slug, so the dry run and the install agree. A
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
        """Plan the entry, then create what the plan marks `create`."""
        entry = await self._catalogue.get(request.entry_id)
        if entry is None:
            raise CatalogueEntryNotFoundError(
                f"Catalogue entry '{request.entry_id}' not found"
            )
        bundle = entry.bundle()
        plan = await plan_bundle(
            bundle, self._presets, self._graph, clash=ClashPolicy.SKIP
        )
        applied = await apply_bundle(plan, bundle, self._presets, self._graph)
        result = InstallOutcome(
            entry_id=entry.id,
            presets_created=applied.created[EntityKind.PRESET],
            presets_skipped=applied.skipped[EntityKind.PRESET],
            item_types_created=applied.created[EntityKind.ITEM_TYPE],
            item_types_skipped=applied.skipped[EntityKind.ITEM_TYPE],
            relationship_types_created=applied.created[EntityKind.RELATIONSHIP_TYPE],
            relationship_types_skipped=applied.skipped[EntityKind.RELATIONSHIP_TYPE],
        )
        logger.info("catalogue entry installed", entry=entry.id)
        return result
