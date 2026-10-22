import uuid
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass, replace
from datetime import date  # noqa: TC003
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.prepare_query import prepare_query, utc_today
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.application.type_catalogue import load_node_types
from app.modules.graph.domain.errors import CollectionNotFoundError
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.query import (
    Condition,
    Cursor,
    FavouriteCondition,
    Group,
    InvalidQueryError,
    Query,
    TextCondition,
    TypeCondition,
)
from app.modules.graph.ports.collection_members import (
    CollectionMembers,
    CollectionSource,
    SmartSource,
)
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


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


def _list_filters(query: ListNodesQuery) -> list[Condition]:
    """The list's own filters as query conditions."""
    filters: list[Condition] = []
    if query.q is not None:
        filters.append(TextCondition(q=query.q))
    if query.type is not None:
        filters.append(TypeCondition(slugs=(query.type,)))
    if query.favourite is not None:
        filters.append(FavouriteCondition(value=query.favourite))
    return filters


def _combine(saved: Group | None, filters: list[Condition]) -> Group | None:
    """AND the saved filter tree with the list filters; None matches everything."""
    children: list[Group | Condition] = [] if saved is None else [saved]
    children.extend(filters)
    return Group(op="and", children=tuple(children)) if children else None


class ListNodes(QueryHandler[GraphRepos, ListNodesQuery, ListNodesResult]):
    """List node with keyset pagination."""

    access: ClassVar[Access] = Content()

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        collection_members: CollectionMembers | None = None,
        today: Callable[[], date] = utc_today,
    ) -> None:
        super().__init__(repos, guard)
        self._collection_members = collection_members
        self._today = today

    async def _resolve_collection(
        self, collection_id: uuid.UUID | None, scope: ContentFilter
    ) -> CollectionSource | None:
        """Resolve a collection to what it holds, or None when unrestricted.

        A collection outside `scope` is not found, like a missing one.
        """
        if collection_id is None:
            return None
        if self._collection_members is None:
            msg = "ListNodes needs collection members to filter by collection"
            raise RuntimeError(msg)
        source = await self._collection_members.resolve(collection_id, scope)
        if source is None:
            msg = f"Collection {collection_id} not found"
            raise CollectionNotFoundError(msg)
        return source

    async def _list_smart(
        self,
        query: ListNodesQuery,
        definition: Mapping[str, Any],
        scope: ContentFilter,
    ) -> ListNodesResult:
        """List a smart collection: its saved query AND the list filters, by id.

        The saved sort is ignored so the id paging holds. A definition that no
        longer validates matches nothing.
        """
        try:
            resolved, _ = await prepare_query(self._repos, definition, self._today())
        except InvalidQueryError as exc:
            logger.info("smart collection query no longer valid", path=exc.path)
            return ListNodesResult(items=[], total=0)
        where = _combine(resolved.query.where, _list_filters(query))
        combined = replace(resolved, query=Query(where=where))
        after = None if query.after is None else Cursor(sort_values=(), id=query.after)
        hits = await self._repos.nodes.search(
            scope=scope, resolved=combined, after=after, limit=query.limit
        )
        total = await self._repos.nodes.search_count(scope=scope, resolved=combined)
        return ListNodesResult(items=[hit.node for hit in hits], total=total)

    async def _search_exclusions(self) -> dict[str, list[str]]:
        """Map each node type slug to the attribute keys a search must skip."""
        exclusions: dict[str, list[str]] = {}
        for node_type in await load_node_types(self._repos):
            keys = search_excluded_keys(node_type.attributes_schema or {})
            if keys:
                exclusions[str(node_type.slug)] = keys
        return exclusions

    async def _handle(self, query: ListNodesQuery, actor: Actor) -> ListNodesResult:
        """Return a page of nodes and total count matching the query."""
        scope = self.scope(actor)
        source = await self._resolve_collection(query.collection, scope)
        if isinstance(source, SmartSource):
            smart = await self._list_smart(query, source.definition, scope)
            logger.debug("nodes listed", count=len(smart.items), total=smart.total)
            return smart
        exclusions = await self._search_exclusions() if query.q is not None else None
        ids = None if source is None else source.ids
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
