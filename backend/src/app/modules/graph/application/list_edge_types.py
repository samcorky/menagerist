import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListEdgeTypesQuery:
    """Request to list edge types with keyset pagination."""

    after: uuid.UUID | None = None
    limit: int = 50


class ListEdgeTypes(QueryHandler[GraphUnitOfWork, ListEdgeTypesQuery, list[EdgeType]]):
    """List edge types with keyset pagination."""

    async def handle(self, query: ListEdgeTypesQuery, actor: Actor) -> list[EdgeType]:
        """Return a page of non-deleted edge types ordered by id."""
        async with self._uow as repos:
            result = await repos.edge_types.list(after=query.after, limit=query.limit)
        logger.debug("edge types listed", count=len(result))
        return result
