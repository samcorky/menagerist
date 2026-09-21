import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CountNodeTypeAttributeUsageQuery:
    """Request to count nodes of a node type that hold an attribute key."""

    node_type_id: uuid.UUID
    key: str
    value: str | None = None


class CountNodeTypeAttributeUsage(
    QueryHandler[GraphRepos, CountNodeTypeAttributeUsageQuery, int]
):
    """Count the nodes of a node type whose attributes contain a key."""

    async def handle(
        self, query: CountNodeTypeAttributeUsageQuery, actor: Actor
    ) -> int:
        """Return the count, or raise `NodeTypeNotFoundError` if the type is missing."""
        node_type = await self._repos.node_types.get(query.node_type_id)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        count = await self._repos.nodes.count_with_attribute(
            str(node_type.slug), query.key, value=query.value
        )
        logger.debug(
            "node type attribute usage counted",
            node_type_id=query.node_type_id,
            key=query.key,
            count=count,
        )
        return count
