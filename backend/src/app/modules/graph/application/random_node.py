"""Pick one of the caller's items at random."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

from app.modules.graph.application.list_nodes import ListNodes, ListNodesQuery
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.item_covers import ItemCovers  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor


@dataclass(frozen=True)
class RandomNodeResult:
    """The item picked, and where its cover thumbnail is if it has one."""

    node: Node
    cover_thumbnail_url: str | None = None


class RandomNode(QueryHandler[GraphRepos, ListNodesQuery, RandomNodeResult]):
    """Return a random item from what `ListNodes` would list.

    Raises `NodeNotFoundError` when nothing matches.

    `after`, `limit` and `q` on the query are ignored.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        lister: ListNodes,
        item_covers: ItemCovers | None = None,
    ) -> None:
        super().__init__(repos, guard)
        self._lister = lister
        self._item_covers = item_covers

    async def _handle(self, query: ListNodesQuery, actor: Actor) -> RandomNodeResult:
        """Return one matching item in the actor's scope, with its cover thumbnail."""
        node = await self._lister.random_node(query, self.scope(actor))
        if node is None:
            msg = "No item matches"
            raise NodeNotFoundError(msg)
        if self._item_covers is None:
            return RandomNodeResult(node=node)
        covers = await self._item_covers.thumbnails([node.id], actor)
        return RandomNodeResult(node=node, cover_thumbnail_url=covers.get(node.id))
