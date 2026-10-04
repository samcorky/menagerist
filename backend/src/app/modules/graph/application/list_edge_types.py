import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.domain.edge_type import EdgeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListEdgeTypesQuery:
    """Request to list edge types with keyset pagination."""

    after: uuid.UUID | None = None
    limit: int = 50


class ListEdgeTypes(QueryHandler[GraphRepos, ListEdgeTypesQuery, list[EdgeType]]):
    """List edge types with keyset pagination."""

    def __init__(
        self, repos: GraphRepos, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(repos)
        self._choice_lists = choice_lists

    async def handle(self, query: ListEdgeTypesQuery, actor: Actor) -> list[EdgeType]:
        """Return a page of non-deleted edge types ordered by id."""
        result = await self._repos.edge_types.list(after=query.after, limit=query.limit)
        logger.debug("edge types listed", count=len(result))
        return [await self._resolved(edge_type) for edge_type in result]

    async def _resolved(self, edge_type: EdgeType) -> EdgeType:
        """Fill in linked options, returning the same object if nothing changed."""
        schema = await resolve_choice_lists(
            edge_type.attributes_schema, self._choice_lists
        )
        if schema is edge_type.attributes_schema:
            return edge_type
        return replace(edge_type, attributes_schema=schema)
