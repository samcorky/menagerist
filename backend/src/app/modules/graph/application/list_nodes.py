import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from app.modules.graph.ports.node_repository import NodeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListNodesQuery:
    """Request for a page of node, ordered by id."""

    after: uuid.UUID | None = None
    limit: int = 50
    type: str | None = None


class ListNodes:
    """List node with keyset pagination."""

    def __init__(self, nodes: NodeRepository) -> None:
        self._nodes = nodes

    async def handle(self, query: ListNodesQuery, actor: Actor) -> list[Node]:
        """Return a page of node after `query.after`, up to `query.limit`."""
        return await self._nodes.list(
            after=query.after, limit=query.limit, type=query.type
        )
