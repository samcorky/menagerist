import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class AttributeValueCountResult:
    """A previously-used attribute value and how many nodes hold it."""

    value: str
    count: int


@dataclass(kw_only=True)
class ListAttributeValuesQuery:
    """Request for the distinct values previously used for an attribute key."""

    node_type_id: uuid.UUID
    key: str
    q: str | None = None
    limit: int = 20


class ListAttributeValues(
    QueryHandler[GraphRepos, ListAttributeValuesQuery, list[AttributeValueCountResult]]
):
    """List distinct string values used for a node type's attribute, most-used first."""

    async def handle(
        self, query: ListAttributeValuesQuery, actor: Actor
    ) -> list[AttributeValueCountResult]:
        """Return the values, or raise `NodeTypeNotFoundError` if missing."""
        node_type = await self._repos.node_types.get(query.node_type_id)
        if node_type is None:
            raise NodeTypeNotFoundError(f"NodeType {query.node_type_id} not found")
        values = await self._repos.nodes.list_attribute_values(
            str(node_type.slug),
            query.key,
            q=query.q,
            limit=query.limit,
        )
        logger.debug(
            "node type attribute values listed",
            node_type_id=query.node_type_id,
            key=query.key,
            count=len(values),
        )
        return [
            AttributeValueCountResult(value=value, count=count)
            for value, count in values
        ]
