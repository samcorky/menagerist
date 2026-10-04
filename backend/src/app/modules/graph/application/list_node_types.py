import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListNodeTypesQuery:
    """Request for a page of node types, ordered by id."""

    after: uuid.UUID | None = None
    limit: int = 50


class ListNodeTypes(QueryHandler[GraphRepos, ListNodeTypesQuery, list[NodeType]]):
    """List node types with keyset pagination."""

    def __init__(
        self, repos: GraphRepos, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(repos)
        self._choice_lists = choice_lists

    async def handle(self, query: ListNodeTypesQuery, actor: Actor) -> list[NodeType]:
        """Return a page of node types after `query.after`, up to `query.limit`."""
        result = await self._repos.node_types.list(after=query.after, limit=query.limit)
        logger.debug("node types listed", count=len(result))
        return [await self._resolved(node_type) for node_type in result]

    async def _resolved(self, node_type: NodeType) -> NodeType:
        """Fill in linked options, returning the same object if nothing changed."""
        schema = await resolve_choice_lists(
            node_type.attributes_schema, self._choice_lists
        )
        if schema is node_type.attributes_schema:
            return node_type
        return replace(node_type, attributes_schema=schema)
