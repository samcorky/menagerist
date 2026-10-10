from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.examples.application.required_by import dependants_by_pack
from app.modules.examples.domain.installation import Installation
from app.modules.examples.domain.pack import PackSummary
from app.modules.examples.ports.pack_catalogue import PackCatalogue  # noqa: TC001
from app.modules.examples.ports.unit_of_work import ExampleRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
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


class ListExamplePacks(
    QueryHandler[ExampleRepos, ListExamplePacksQuery, list[ExamplePackStatus]]
):
    """List the shipped packs and which of them are installed."""

    def __init__(self, repos: ExampleRepos, catalogue: PackCatalogue) -> None:
        """Initialise with the example repositories and the pack catalogue."""
        super().__init__(repos)
        self._catalogue = catalogue

    async def handle(
        self,
        query: ListExamplePacksQuery,
        actor: Actor,
    ) -> list[ExamplePackStatus]:
        """Return one status per shipped pack, in catalogue order.

        `required_by` holds the installed add-ons (a half-finished installation
        counts) that need the pack.
        """
        active = {i.pack_id: i for i in await self._repos.installations.list_active()}
        packs = await self._catalogue.list_packs()
        by_id = {s.id: s for s in packs}
        dependants = dependants_by_pack(packs, active.keys())
        return [
            ExamplePackStatus(
                summary=s,
                installation=active.get(s.id),
                requires=tuple(by_id[r] for r in s.requires if r in by_id),
                required_by=tuple(dependants.get(s.id, [])),
            )
            for s in packs
        ]
