import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_TYPE_PAGE_SIZE = 100


@dataclass(kw_only=True)
class ListNodesQuery:
    """Request for a page of node, ordered by id."""

    after: uuid.UUID | None = None
    limit: int = 50
    type: str | None = None
    q: str | None = None
    favourite: bool | None = None


@dataclass(frozen=True)
class ListNodesResult:
    """Paginated node list with the total number of matching nodes."""

    items: list[Node]
    total: int


class ListNodes(QueryHandler[GraphRepos, ListNodesQuery, ListNodesResult]):
    """List node with keyset pagination."""

    async def _search_exclusions(self) -> dict[str, list[str]]:
        """Map each node type slug to the attribute keys a search must skip."""
        exclusions: dict[str, list[str]] = {}
        after: uuid.UUID | None = None
        while True:
            page = await self._repos.node_types.list(after=after, limit=_TYPE_PAGE_SIZE)
            for node_type in page:
                keys = search_excluded_keys(node_type.attributes_schema or {})
                if keys:
                    exclusions[str(node_type.slug)] = keys
            if len(page) < _TYPE_PAGE_SIZE:
                return exclusions
            after = page[-1].id

    async def handle(self, query: ListNodesQuery, actor: Actor) -> ListNodesResult:
        """Return a page of nodes and total count matching the query."""
        exclusions = await self._search_exclusions() if query.q is not None else None
        items = await self._repos.nodes.list(
            after=query.after,
            limit=query.limit,
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
        )
        total = await self._repos.nodes.count(
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
        )
        result = ListNodesResult(items=items, total=total)
        logger.debug("nodes listed", count=len(result.items), total=result.total)
        return result
