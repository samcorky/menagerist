import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetNodeTypeQuery:
    """Request to fetch a single node type by id."""

    node_type_id: uuid.UUID


class GetNodeType(QueryHandler[GraphRepos, GetNodeTypeQuery, NodeType]):
    """Fetch a single node type by id."""

    async def handle(self, query: GetNodeTypeQuery, actor: Actor) -> NodeType:
        """Return the node type, or raise `NodeTypeNotFoundError` if missing."""
        node_type = await self._repos.node_types.get(query.node_type_id)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        logger.debug("node type fetched", node_type_id=query.node_type_id)
        return node_type
