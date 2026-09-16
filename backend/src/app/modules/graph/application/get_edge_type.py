import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetEdgeTypeQuery:
    """Request to retrieve a single edge type."""

    edge_type_id: uuid.UUID


class GetEdgeType(QueryHandler[GraphRepos, GetEdgeTypeQuery, EdgeType]):
    """Retrieve a single edge type by id."""

    async def handle(self, query: GetEdgeTypeQuery, actor: Actor) -> EdgeType:
        """Return the edge type or raise EdgeTypeNotFoundError."""
        edge_type = await self._repos.edge_types.get(query.edge_type_id)
        if edge_type is None:
            raise EdgeTypeNotFoundError(f"Edge type {query.edge_type_id} not found")
        logger.debug("edge type fetched", edge_type_id=query.edge_type_id)
        return edge_type
