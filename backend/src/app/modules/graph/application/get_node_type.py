import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.choice_lists import resolve_choice_lists
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.domain.node_type import NodeType

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.choice_list_source import ChoiceListSource  # noqa: TC001
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

    def __init__(
        self, repos: GraphRepos, choice_lists: ChoiceListSource | None = None
    ) -> None:
        super().__init__(repos)
        self._choice_lists = choice_lists

    async def handle(self, query: GetNodeTypeQuery, actor: Actor) -> NodeType:
        """Return the node type, or raise `NodeTypeNotFoundError` if missing."""
        node_type = await self._repos.node_types.get(query.node_type_id)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        logger.debug("node type fetched", node_type_id=query.node_type_id)
        resolved = await resolve_choice_lists(
            node_type.attributes_schema, self._choice_lists
        )
        if resolved is node_type.attributes_schema:
            return node_type
        return replace(node_type, attributes_schema=resolved)
