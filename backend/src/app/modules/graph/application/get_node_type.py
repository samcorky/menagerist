import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetNodeTypeQuery:
    """Request to fetch a single node type by id."""

    node_type_id: uuid.UUID


class GetNodeType(QueryHandler[GraphUnitOfWork, GetNodeTypeQuery, NodeType]):
    """Fetch a single node type by id."""

    async def handle(self, query: GetNodeTypeQuery, actor: Actor) -> NodeType:
        """Return the node type, or raise `NodeTypeNotFoundError` if missing."""
        async with self._uow as repos:
            node_type = await repos.node_types.get(query.node_type_id)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        return node_type
