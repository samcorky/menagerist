import uuid
from collections.abc import Callable  # noqa: TC003
from dataclasses import dataclass, field, replace
from datetime import date  # noqa: TC003
from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.application.prepare_query import prepare_query, utc_today
from app.modules.graph.application.schema_meta import search_excluded_keys
from app.modules.graph.application.search_nodes import TOTAL_CAP
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
    ResolvedQuery,
    SortKey,
    TextCondition,
    TypeCondition,
    TypeCount,
)
from app.modules.graph.ports.collection_members import (
    CollectionMembers,
    CollectionSource,
    SmartSource,
)
from app.modules.graph.ports.item_covers import ItemCovers  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.errors import ValidationError
from app.shared_kernel.paging import (
    Cursor as PageCursor,
    InvalidCursorError,
    PageRequest,
    SearchedPagedQuery,
    SortOrder,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


class NodeSort(StrEnum):
    """What a list of items can be sorted by: fields of the response."""

    NAME = "name"
    TYPE = "type"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


# What the search engine can order a smart collection by.
_SMART_SORTS = {
    NodeSort.NAME: "name",
    NodeSort.CREATED_AT: "created",
    NodeSort.UPDATED_AT: "updated",
}


@dataclass(kw_only=True)
class ListNodesQuery(SearchedPagedQuery[NodeSort]):
    """Request for a page of items, by id unless `sort` says otherwise."""

    type: str | None = None
    favourite: bool | None = None
    collection: uuid.UUID | None = None


@dataclass(frozen=True)
class ListNodesResult:
    """Paginated node list with the total number of matching nodes."""

    items: list[Node]
    total: int
    total_capped: bool = False
    covers: dict[uuid.UUID, str] = field(default_factory=dict)
    next: PageCursor | None = None


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

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    def __init__(
        self,
        repos: GraphRepos,
        guard: AccessGuard,
        collection_members: CollectionMembers | None = None,
        item_covers: ItemCovers | None = None,
        today: Callable[[], date] = utc_today,
        total_cap: int = TOTAL_CAP,
    ) -> None:
        super().__init__(repos, guard)
        self._collection_members = collection_members
        self._item_covers = item_covers
        self._today = today
        self._total_cap = total_cap

    def _cap(self, query: ListNodesQuery) -> int | None:
        """Text search counts stop at the cap; other lists count exactly."""
        return None if query.q is None else self._total_cap

    @staticmethod
    def _capped(counted: int, cap: int | None) -> tuple[int, bool]:
        """Clamp a count taken with one past `cap` and say whether it was clamped."""
        if cap is None:
            return counted, False
        return min(counted, cap), counted > cap

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

    async def _smart_query(
        self,
        query: ListNodesQuery,
        definition: Mapping[str, Any],
        scope: ContentFilter,
    ) -> ResolvedQuery | None:
        """A smart collection's saved query ANDed with the list filters.

        None when the definition no longer validates, which matches nothing.
        """
        try:
            resolved, _ = await prepare_query(
                self._repos, definition, self._today(), scope=scope
            )
        except InvalidQueryError as exc:
            logger.info("smart collection query no longer valid", path=exc.path)
            return None
        where = _combine(resolved.query.where, _list_filters(query))
        return replace(resolved, query=Query(where=where))

    @staticmethod
    def _page_request(query: ListNodesQuery) -> PageRequest:
        return query.page_request()

    @staticmethod
    def _smart_sort(query: ListNodesQuery) -> tuple[SortKey, ...]:
        """The search engine's ordering for a smart collection's list.

        Raises:
            ValidationError: The sort is one the engine cannot give, or a direction
                is asked for without saying what to sort by.
        """
        if query.sort is None:
            if query.order is SortOrder.DESC:
                msg = "Say what to sort a smart collection by to list it newest first."
                raise ValidationError(msg)
            return ()
        by = _SMART_SORTS.get(query.sort)
        if by is None:
            msg = "A smart collection sorts by name, created_at or updated_at."
            raise ValidationError(msg)
        return (SortKey(by=by, dir=query.order.value),)  # type: ignore[arg-type]

    @staticmethod
    def _smart_cursor(query: ListNodesQuery) -> Cursor | None:
        """The search engine's cursor for `query.after`, checked against the sort."""
        after = query.after
        if after is None:
            return None
        numeric = query.sort in {NodeSort.CREATED_AT, NodeSort.UPDATED_AT}
        for value in after.values:
            if isinstance(value, bool) or not (
                isinstance(value, int | float) if numeric else isinstance(value, str)
            ):
                msg = "The page cursor is not valid."
                raise InvalidCursorError(msg)
        return Cursor(sort_values=after.values, id=after.id)

    async def _list_smart(
        self,
        query: ListNodesQuery,
        definition: Mapping[str, Any],
        scope: ContentFilter,
    ) -> ListNodesResult:
        """List a smart collection: its saved query AND the list filters.

        The saved sort is replaced by the list's own, by id unless `sort` is given.
        """
        request = self._page_request(query)
        request.check()
        sort = self._smart_sort(query)
        after = self._smart_cursor(query)
        combined = await self._smart_query(query, definition, scope)
        if combined is None:
            return ListNodesResult(items=[], total=0)
        combined = replace(combined, query=replace(combined.query, sort=sort))
        hits = await self._repos.nodes.search(
            scope=scope, resolved=combined, after=after, limit=request.size + 1
        )
        kept = hits[: request.size]
        next_cursor = (
            request.next_after(kept[-1].node.id, tuple(kept[-1].sort_values))
            if kept and len(hits) > request.size
            else None
        )
        cap = self._cap(query)
        counted = await self._repos.nodes.search_count(
            scope=scope,
            resolved=combined,
            limit=None if cap is None else cap + 1,
        )
        total, capped = self._capped(counted, cap)
        return ListNodesResult(
            items=[hit.node for hit in kept],
            total=total,
            total_capped=capped,
            next=next_cursor,
        )

    async def count_exact(self, query: ListNodesQuery, scope: ContentFilter) -> int:
        """Count what the list filters match, uncapped and without fetching rows.

        The caller has already passed the access check.
        """
        source = await self._resolve_collection(query.collection, scope)
        if isinstance(source, SmartSource):
            combined = await self._smart_query(query, source.definition, scope)
            if combined is None:
                return 0
            return await self._repos.nodes.search_count(scope=scope, resolved=combined)
        exclusions = (
            await self._search_exclusions(scope) if query.q is not None else None
        )
        return await self._repos.nodes.count(
            scope=scope,
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
            ids=None if source is None else source.ids,
        )

    async def count_types(
        self, collection_id: uuid.UUID | None, scope: ContentFilter
    ) -> list[TypeCount]:
        """Count the items per item type, on one collection or all of them.

        The caller has already passed the access check.
        """
        source = await self._resolve_collection(collection_id, scope)
        if isinstance(source, SmartSource):
            combined = await self._smart_query(
                ListNodesQuery(), source.definition, scope
            )
            if combined is None:
                return []
            return await self._repos.nodes.count_by_type(scope=scope, resolved=combined)
        return await self._repos.nodes.count_by_type(
            scope=scope, ids=None if source is None else source.ids
        )

    async def random_node(
        self, query: ListNodesQuery, scope: ContentFilter
    ) -> Node | None:
        """Pick one item the list filters match at random, or None if there is none.

        The caller has already passed the access check. `q` is not applied: a
        random pick from a text search is not wanted.
        """
        source = await self._resolve_collection(query.collection, scope)
        if isinstance(source, SmartSource):
            combined = await self._smart_query(query, source.definition, scope)
            if combined is None:
                return None
            return await self._repos.nodes.random(scope=scope, resolved=combined)
        return await self._repos.nodes.random(
            scope=scope,
            type=query.type,
            favourite=query.favourite,
            ids=None if source is None else source.ids,
        )

    async def _search_exclusions(self, scope: ContentFilter) -> dict[str, list[str]]:
        """Map each node type slug to the attribute keys a search must skip."""
        exclusions: dict[str, list[str]] = {}
        for node_type in await load_node_types(self._repos, scope):
            keys = search_excluded_keys(node_type.attributes_schema or {})
            if keys:
                exclusions[str(node_type.slug)] = keys
        return exclusions

    async def _with_covers(
        self, result: ListNodesResult, actor: Actor
    ) -> ListNodesResult:
        """Add the cover thumbnail of each listed item that has one."""
        if self._item_covers is None or not result.items:
            return result
        covers = await self._item_covers.thumbnails(
            [node.id for node in result.items], actor
        )
        return replace(result, covers=covers)

    async def _handle(self, query: ListNodesQuery, actor: Actor) -> ListNodesResult:
        """Return a page of nodes and total count matching the query."""
        scope = self.scope(actor)
        source = await self._resolve_collection(query.collection, scope)
        if isinstance(source, SmartSource):
            smart = await self._list_smart(query, source.definition, scope)
            logger.debug("nodes listed", count=len(smart.items), total=smart.total)
            return await self._with_covers(smart, actor)
        exclusions = (
            await self._search_exclusions(scope) if query.q is not None else None
        )
        ids = None if source is None else source.ids
        page = await self._repos.nodes.page(
            scope=scope,
            page=self._page_request(query),
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
            ids=ids,
        )
        cap = self._cap(query)
        counted = await self._repos.nodes.count(
            scope=scope,
            type=query.type,
            q=query.q,
            favourite=query.favourite,
            attribute_search_exclusions=exclusions,
            ids=ids,
            limit=None if cap is None else cap + 1,
        )
        total, capped = self._capped(counted, cap)
        result = await self._with_covers(
            ListNodesResult(
                items=page.items, total=total, total_capped=capped, next=page.next
            ),
            actor,
        )
        logger.debug("nodes listed", count=len(result.items), total=result.total)
        return result
