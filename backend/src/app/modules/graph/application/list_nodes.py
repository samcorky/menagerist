import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.domain.errors import CollectionNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.collection_members import CollectionMembers  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.access_policy import AccessPolicy  # noqa: TC001
from app.shared_kernel.cqrs import ScopedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_scope import AccessScope
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
    collection: uuid.UUID | None = None


@dataclass(frozen=True)
class ListNodesResult:
    """Paginated node list with the total number of matching nodes."""

    items: list[Node]
    total: int


class ListNodes(ScopedQueryHandler[GraphRepos, ListNodesQuery, ListNodesResult]):
    """List node with keyset pagination."""

    def __init__(
        self,
        repos: GraphRepos,
        policy: AccessPolicy,
        collection_members: CollectionMembers | None = None,
    ) -> None:
        super().__init__(repos, policy)
        self._collection_members = collection_members

    async def _collection_item_ids(
        self, collection_id: uuid.UUID | None, scope: AccessScope
    ) -> set[uuid.UUID] | None:
        """Resolve a collection to its item ids, or None when unrestricted.

        A collection outside `scope` is not found, like a missing one.
        """
        if collection_id is None:
            return None
        if self._collection_members is None:
            msg = "ListNodes needs collection members to filter by collection"
            raise RuntimeError(msg)
        ids = await self._collection_members.item_ids(collection_id, scope)
        if ids is None:
            msg = f"Collection {collection_id} not found"
            raise CollectionNotFoundError(msg)
        return ids

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
        scope = self._policy.scope_for(actor)
        ids = await self._collection_item_ids(query.collection, scope)
        items = await self._repos.nodes.list(
            scope=scope,
            after=query.after,
            limit=query.limit,
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
            ids=ids,
        )
        total = await self._repos.nodes.count(
            scope=scope,
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
            ids=ids,
        )
        result = ListNodesResult(items=items, total=total)
        logger.debug("nodes listed", count=len(result.items), total=result.total)
        return result
