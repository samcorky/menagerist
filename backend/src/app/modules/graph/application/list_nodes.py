import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListNodesQuery:
    """Request for a page of node, ordered by id."""

    after: uuid.UUID | None = None
    limit: int = 50
    type: str | None = None
    q: str | None = None
    favourite: bool | None = None


@dataclass(frozen=True)
class ListNodesResult:
    """Paginated node list with the total number of matching nodes."""

    items: list[Node]
    total: int


class ListNodes(QueryHandler[GraphUnitOfWork, ListNodesQuery, ListNodesResult]):
    """List node with keyset pagination."""

    async def handle(self, query: ListNodesQuery, actor: Actor) -> ListNodesResult:
        """Return a page of nodes and total count matching the query."""
        async with self._uow as repos:
            items = await repos.nodes.list(
                after=query.after,
                limit=query.limit,
                type=query.type,
                q=query.q,
                favourite=query.favourite,
            )
            total = await repos.nodes.count(
                type=query.type,
                q=query.q,
                favourite=query.favourite,
            )
        return ListNodesResult(items=items, total=total)
