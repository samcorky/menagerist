from dataclasses import dataclass
from typing import TYPE_CHECKING

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
    """A shipped pack and its active installation, if any."""

    summary: PackSummary
    installation: Installation | None


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
        """Return one status per shipped pack, in catalogue order."""
        active = {i.pack_id: i for i in await self._repos.installations.list_active()}
        return [
            ExamplePackStatus(summary=s, installation=active.get(s.id))
            for s in await self._catalogue.list_packs()
        ]
