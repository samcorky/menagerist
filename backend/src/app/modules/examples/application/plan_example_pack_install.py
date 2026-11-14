from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.examples.application.install_plan import plan_install
from app.modules.examples.application.permissions import ExamplePermission
from app.modules.examples.domain.errors import PackNotFoundError
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.modules.transfer.application.removal import RemovalTargets
from app.modules.transfer.domain.entity_kind import EntityKind
from app.modules.transfer.domain.plan import Plan
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.modules.examples.ports.cover_target import CoverTarget
    from app.modules.transfer.ports.targets import (
        CollectionTarget,
        GraphTarget,
        PresetTarget,
    )
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class PlanExamplePackInstallQuery:
    """Request to see what installing a shipped example pack would do."""

    pack_id: str


class PlanExamplePackInstall(
    QueryHandler[ExampleRepos, PlanExamplePackInstallQuery, Plan]
):
    """Report what installing a pack would create, take back and refuse.

    A dry run of `InstallExamplePack`: the same plan, and nothing is written. The
    install refuses exactly when this report is not `ready`.

    Raises:
        PackNotFoundError: the catalogue has no such pack.
    """

    access: ClassVar[Access] = Content(ExamplePermission.PACK_INSTALL)

    def __init__(
        self,
        repos: ExampleRepos,
        guard: AccessGuard,
        catalogue: PackCatalogue,
        presets: PresetTarget,
        graph: GraphTarget,
        collections: CollectionTarget,
        covers: CoverTarget,
    ) -> None:
        """Initialise with the repositories, policy, catalogue and four targets."""
        super().__init__(repos, guard)
        self._catalogue = catalogue
        self._covers = covers
        self._targets = RemovalTargets(
            presets=presets,
            graph=graph,
            collections=collections,
            others={EntityKind.COVER: covers},
        )

    async def _handle(self, query: PlanExamplePackInstallQuery, actor: Actor) -> Plan:
        """Plan the install and return its report."""
        pack = await self._catalogue.get(query.pack_id)
        if pack is None:
            raise PackNotFoundError(f"Example pack '{query.pack_id}' not found")
        plan = await plan_install(
            pack,
            runs=self._repos.runs,
            scope=self.scope(actor),
            catalogue=self._catalogue,
            targets=self._targets,
            covers=self._covers,
        )
        return plan.report
