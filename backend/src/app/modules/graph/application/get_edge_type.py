import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetEdgeTypeQuery:
    """Request to retrieve a single edge type."""

    edge_type_id: uuid.UUID


class GetEdgeType(QueryHandler[GraphUnitOfWork, GetEdgeTypeQuery, EdgeType]):
    """Retrieve a single edge type by id."""

    async def handle(self, query: GetEdgeTypeQuery, actor: Actor) -> EdgeType:
        """Return the edge type or raise EdgeTypeNotFoundError."""
        async with self._uow as repos:
            edge_type = await repos.edge_types.get(query.edge_type_id)
        if edge_type is None:
            raise EdgeTypeNotFoundError(f"Edge type {query.edge_type_id} not found")
        return edge_type
