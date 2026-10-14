from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.examples.application.required_by import dependants_by_pack
from app.modules.examples.domain.installation import Installation
from app.modules.examples.domain.pack import PackSummary
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.cqrs import ScopedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_policy import AccessPolicy
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListExamplePacksQuery:
    """Request to list the shipped packs with their installation state."""


@dataclass(kw_only=True, frozen=True, eq=False)
class ExamplePackStatus:
    """A shipped pack, its active installation, and how it relates to other packs."""

    summary: PackSummary
    installation: Installation | None
    requires: tuple[PackSummary, ...] = ()
    required_by: tuple[PackSummary, ...] = ()
    links_with: tuple[PackSummary, ...] = ()


class ListExamplePacks(
    ScopedQueryHandler[ExampleRepos, ListExamplePacksQuery, list[ExamplePackStatus]]
):
    """List the shipped packs and which of them are installed."""

    def __init__(
        self, repos: ExampleRepos, policy: AccessPolicy, catalogue: PackCatalogue
    ) -> None:
        """Initialise with the repositories, access policy and pack catalogue."""
        super().__init__(repos, policy)
        self._catalogue = catalogue

    async def handle(
        self,
        query: ListExamplePacksQuery,
        actor: Actor,
    ) -> list[ExamplePackStatus]:
        """Return one status per shipped pack, in catalogue order.

        Only the actor's own installations count. `required_by` holds the installed
        add-ons (a half-finished installation counts) that need the pack.
        """
        installations = await self._repos.installations.list_active(
            scope=self._policy.scope_for(actor)
        )
        active = {i.pack_id: i for i in installations}
        packs = await self._catalogue.list_packs()
        by_id = {s.id: s for s in packs}
        dependants = dependants_by_pack(packs, active.keys())
        return [
            ExamplePackStatus(
                summary=s,
                installation=active.get(s.id),
                requires=tuple(by_id[r] for r in s.requires if r in by_id),
                required_by=tuple(dependants.get(s.id, [])),
                links_with=tuple(by_id[r] for r in s.links_with if r in by_id),
            )
            for s in packs
        ]
