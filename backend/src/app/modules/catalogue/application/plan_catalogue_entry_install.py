from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.catalogue.application.permissions import CataloguePermission
from app.modules.catalogue.domain.errors import CatalogueEntryNotFoundError
from app.modules.catalogue.ports.entry_catalogue import EntryCatalogue  # noqa: TC001
from app.modules.transfer.application.pipeline import plan_bundle
from app.modules.transfer.domain.plan import ClashPolicy, Plan
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.cqrs import UseCase

if TYPE_CHECKING:
    from app.modules.transfer.ports.targets import GraphTarget, PresetTarget
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class PlanCatalogueEntryInstallQuery:
    """Request to see what installing one entry would do, without installing it."""

    entry_id: str


class PlanCatalogueEntryInstall(UseCase[PlanCatalogueEntryInstallQuery, Plan]):
    """Return the plan `InstallCatalogueEntry` would apply; nothing is written.

    It needs the install permission, as the plan is part of installing.

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
        self, request: PlanCatalogueEntryInstallQuery, actor: Actor
    ) -> Plan:
        """Plan the entry against what the person already has."""
        entry = await self._catalogue.get(request.entry_id)
        if entry is None:
            raise CatalogueEntryNotFoundError(
                f"Catalogue entry '{request.entry_id}' not found"
            )
        return await plan_bundle(
            entry.bundle(), self._presets, self._graph, clash=ClashPolicy.SKIP
        )
