import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.modules.graph.domain.node_type import NodeType
    from app.modules.graph.ports.node_type_repository import NodeTypeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListNodeTypesQuery:
    """Request for a page of node types, ordered by id."""

    after: uuid.UUID | None = None
    limit: int = 50


class ListNodeTypes:
    """List node types with keyset pagination."""

    def __init__(self, node_types: NodeTypeRepository) -> None:
        self._node_types = node_types

    async def handle(self, query: ListNodeTypesQuery, actor: Actor) -> list[NodeType]:
        """Return a page of node types after `query.after`, up to `query.limit`."""
        return await self._node_types.list(after=query.after, limit=query.limit)
