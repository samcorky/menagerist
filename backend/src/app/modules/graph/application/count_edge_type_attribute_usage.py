import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CountEdgeTypeAttributeUsageQuery:
    """Request to count edges of a edge type that hold an attribute key."""

    edge_type_id: uuid.UUID
    key: str


class CountEdgeTypeAttributeUsage(
    QueryHandler[GraphRepos, CountEdgeTypeAttributeUsageQuery, int]
):
    """Count the edges of a edge type whose attributes contain a key."""

    async def handle(
        self, query: CountEdgeTypeAttributeUsageQuery, actor: Actor
    ) -> int:
        """Return the count, or raise `EdgeTypeNotFoundError` if the type is missing."""
        edge_type = await self._repos.edge_types.get(query.edge_type_id)
        if edge_type is None:
            raise EdgeTypeNotFoundError(f"EdgeType {query.edge_type_id} not found")
        count = await self._repos.edges.count_with_attribute(
            str(edge_type.slug), query.key
        )
        logger.debug(
            "edge type attribute usage counted",
            edge_type_id=query.edge_type_id,
            key=query.key,
            count=count,
        )
        return count
