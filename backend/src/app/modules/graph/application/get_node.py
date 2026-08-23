import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import NodeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from app.modules.graph.ports.node_repository import NodeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetNodeQuery:
    """Request for a single node by id."""

    node_id: uuid.UUID


class GetNode:
    """Fetch a single node by id."""

    def __init__(self, nodes: NodeRepository) -> None:
        self._nodes = nodes

    async def handle(self, query: GetNodeQuery, actor: Actor) -> Node:
        """Return the requested node, raising `NodeNotFoundError` if it's missing."""
        node = await self._nodes.get(query.node_id)
        if node is None:
            raise NodeNotFoundError(f"Node {query.node_id} not found")
        return node
