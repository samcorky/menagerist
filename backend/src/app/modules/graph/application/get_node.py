import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.domain.errors import NodeNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetNodeQuery:
    """Request for a single node by id."""

    node_id: uuid.UUID


class GetNode(GuardedQueryHandler[GraphRepos, GetNodeQuery, Node]):
    """Fetch a single node by id."""

    access: ClassVar[Access] = Content()

    async def _handle(self, query: GetNodeQuery, actor: Actor) -> Node:
        """Return the requested node, raising `NodeNotFoundError` if it's missing."""
        node = await self._repos.nodes.get(query.node_id, scope=self.scope(actor))
        if node is None:
            raise NodeNotFoundError(f"Node {query.node_id} not found")
        self._guard.assert_can_view(actor, node.owner_id)
        logger.debug("node fetched", node_id=query.node_id)
        return node
