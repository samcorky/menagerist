from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import EdgeTypeNotFoundError

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge_type import EdgeType
    from app.modules.graph.ports.edge_type_repository import EdgeTypeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class GetEdgeTypeQuery:
    """Request to retrieve a single edge type."""

    edge_type_id: "uuid.UUID"


class GetEdgeType:
    """Retrieve a single edge type by id."""

    def __init__(self, edge_types: EdgeTypeRepository) -> None:
        self._edge_types = edge_types

    async def handle(self, query: GetEdgeTypeQuery, actor: Actor) -> EdgeType:
        """Return the edge type or raise EdgeTypeNotFoundError."""
        edge_type = await self._edge_types.get(query.edge_type_id)
        if edge_type is None:
            raise EdgeTypeNotFoundError(f"Edge type {query.edge_type_id} not found")
        return edge_type
