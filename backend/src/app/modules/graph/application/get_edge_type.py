import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.domain.edge_type import EdgeType
from app.modules.graph.domain.errors import EdgeTypeNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
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

    def __init__(
        self, repos: GraphRepos, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(repos)
        self._choice_lists = choice_lists

    async def handle(self, query: GetEdgeTypeQuery, actor: Actor) -> EdgeType:
        """Return the edge type or raise EdgeTypeNotFoundError."""
        edge_type = await self._repos.edge_types.get(query.edge_type_id)
        if edge_type is None:
            raise EdgeTypeNotFoundError(f"Edge type {query.edge_type_id} not found")
        logger.debug("edge type fetched", edge_type_id=query.edge_type_id)
        resolved = await resolve_choice_lists(
            edge_type.attributes_schema, self._choice_lists
        )
        if resolved is edge_type.attributes_schema:
            return edge_type
        return replace(edge_type, attributes_schema=resolved)
