import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.node_type import NodeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class ListNodeTypesQuery:
    """Request for a page of node types, ordered by id."""

    after: uuid.UUID | None = None
    limit: int = 50


class ListNodeTypes(QueryHandler[GraphUnitOfWork, ListNodeTypesQuery, list[NodeType]]):
    """List node types with keyset pagination."""

    async def handle(self, query: ListNodeTypesQuery, actor: Actor) -> list[NodeType]:
        """Return a page of node types after `query.after`, up to `query.limit`."""
        async with self._uow as repos:
            return await repos.node_types.list(after=query.after, limit=query.limit)
