import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import NodeTypeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.node_type_repository import NodeTypeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetNodeTypeQuery:
    """Request to fetch a single node type by id."""

    node_type_id: uuid.UUID


class GetNodeType:
    """Fetch a single node type by id."""

    def __init__(self, node_types: NodeTypeRepository) -> None:
        self._node_types = node_types

    async def handle(self, query: GetNodeTypeQuery, actor: Actor) -> NodeType:
        """Return the node type, or raise `NodeTypeNotFoundError` if missing."""
        node_type = await self._node_types.get(query.node_type_id)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        return node_type
