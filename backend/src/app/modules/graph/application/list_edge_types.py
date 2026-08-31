from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.domain.edge_type import EdgeType
    from app.modules.graph.ports.edge_type_repository import EdgeTypeRepository
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListEdgeTypesQuery:
    """Request to list edge types with keyset pagination."""

    after: "uuid.UUID | None" = None
    limit: int = 50


class ListEdgeTypes:
    """List edge types with keyset pagination."""

    def __init__(self, edge_types: EdgeTypeRepository) -> None:
        self._edge_types = edge_types

    async def handle(self, query: ListEdgeTypesQuery, actor: Actor) -> list[EdgeType]:
        """Return a page of non-deleted edge types ordered by id."""
        return await self._edge_types.list(after=query.after, limit=query.limit)
