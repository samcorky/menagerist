import uuid
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.get_collection import (
    CollectionSummary,
    summarise,
)
from app.modules.collections.application.permissions import CollectionPermission

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.domain.collection import CollectionKind
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Cursor, Page, PagedQuery, PageRequest

if TYPE_CHECKING:
    from app.modules.collections.domain.collection import Collection
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


class CollectionSort(StrEnum):
    """What a list of collections can be sorted by: fields of the response."""

    NAME = "name"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(kw_only=True)
class ListCollectionsQuery(PagedQuery[CollectionSort]):
    """Request for a page of collections, optionally holding an item.

    Collections come by id unless `sort` says otherwise; `order` sets the
    direction. A `kind` keeps one kind only; the other kind is not loaded or
    counted. `item_id` keeps the collections that item is in: manual ones holding
    it and smart ones whose definition matches it.
    """

    item_id: uuid.UUID | None = None
    q: str | None = None
    kind: CollectionKind | None = None


@dataclass(kw_only=True, frozen=True)
class ListCollectionsResult:
    """A page of collection summaries, and the cursor of the next page if any."""

    items: list[CollectionSummary]
    next: Cursor | None = None


class ListCollections(
    QueryHandler[CollectionsRepos, ListCollectionsQuery, ListCollectionsResult]
):
    """List collections with keyset pagination and live item counts."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_READ)

    def __init__(
        self, repos: CollectionsRepos, guard: AccessGuard, items: ItemLookup
    ) -> None:
        super().__init__(repos, guard)
        self._items = items

    async def _handle(
        self, query: ListCollectionsQuery, actor: Actor
    ) -> ListCollectionsResult:
        """Return a page of collections after `query.after`, up to `query.limit`."""
        scope = self.scope(actor)
        page = await self._page(query, scope)
        summaries = [
            await summarise(self._repos, self._items, c, scope) for c in page.items
        ]
        logger.debug("collections listed", count=len(summaries))
        return ListCollectionsResult(items=summaries, next=page.next)

    async def _page(
        self, query: ListCollectionsQuery, scope: ContentFilter
    ) -> Page[Collection]:
        """Return up to `query.limit` collections, keeping only those holding the item.

        Filtering happens while paging so a page is never short just because
        non-matching collections sat between matches. The next cursor is the end of
        the last row looked at, and is given only when a later collection holds the
        item too, so the last page never points to an empty one.
        """
        request = query.page_request()
        if query.item_id is None:
            return await self._repos.collections.list(
                scope=scope, page=request, q=query.q, kind=query.kind
            )
        item_id = query.item_id
        holding = (
            set()
            if query.kind is CollectionKind.DYNAMIC
            else await self._repos.memberships.collection_ids_for(item_id, scope=scope)
        )
        found: list[Collection] = []
        while True:
            # Never ask for more rows than the page still needs, so the cursor of
            # the last batch is the cursor of the last row kept.
            batch = await self._repos.collections.list(
                scope=scope,
                page=replace(request, limit=query.limit - len(found)),
                q=query.q,
                kind=query.kind,
            )
            found.extend(await self._holding(batch.items, item_id, holding, scope))
            if batch.next is None:
                return Page(items=found)
            request = replace(request, after=batch.next)
            if len(found) == query.limit:
                more = await self._any_holding(query, request, item_id, holding, scope)
                return Page(items=found, next=request.after if more else None)

    async def _any_holding(
        self,
        query: ListCollectionsQuery,
        request: PageRequest,
        item_id: uuid.UUID,
        holding: set[uuid.UUID],
        scope: ContentFilter,
    ) -> bool:
        """Whether any collection from `request` onwards holds the item."""
        request = replace(request, limit=query.limit)
        while True:
            batch = await self._repos.collections.list(
                scope=scope, page=request, q=query.q, kind=query.kind
            )
            if await self._holding(batch.items, item_id, holding, scope):
                return True
            if batch.next is None:
                return False
            request = replace(request, after=batch.next)

    async def _holding(
        self,
        collections: list[Collection],
        item_id: uuid.UUID,
        holding: set[uuid.UUID],
        scope: ContentFilter,
    ) -> list[Collection]:
        """The collections the item is in."""
        return [c for c in collections if await self._holds(c, item_id, holding, scope)]

    async def _holds(
        self,
        collection: Collection,
        item_id: uuid.UUID,
        holding: set[uuid.UUID],
        scope: ContentFilter,
    ) -> bool:
        """Whether the item is in the collection: held if manual, matched if smart."""
        if collection.kind is CollectionKind.MANUAL:
            return collection.id in holding
        if collection.definition is None:
            return False
        return await self._items.matches(collection.definition, scope, item_id)
