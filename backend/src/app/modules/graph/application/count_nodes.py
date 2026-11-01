"""Count the items matching the list's filters exactly."""

from typing import TYPE_CHECKING, ClassVar

from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


class CountNodes(QueryHandler[GraphRepos, ListNodesQuery, int]):
    """Count the items `ListNodes` would list, with no cap.

    `after` and `limit` on the query are ignored.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    def __init__(
        self, repos: GraphRepos, guard: AccessGuard, lister: ListNodes
    ) -> None:
        super().__init__(repos, guard)
        self._lister = lister

    async def _handle(self, query: ListNodesQuery, actor: Actor) -> int:
        """Return the exact count in the actor's scope."""
        return await self._lister.count_exact(query, self.scope(actor))
