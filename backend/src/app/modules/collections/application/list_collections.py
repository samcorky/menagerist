import uuid
from dataclasses import dataclass
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

if TYPE_CHECKING:
    from app.modules.collections.domain.collection import Collection
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor
    from app.shared_kernel.content_filter import ContentFilter

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListCollectionsQuery:
    """Request for a page of collections ordered by id, optionally holding an item.

    A `kind` keeps one kind only; the other kind is not loaded or counted.
    `item_id` keeps manual collections holding that item; `matches_item` keeps
    smart collections whose definition matches it, so implies the smart kind.
    """

    after: uuid.UUID | None = None
    limit: int = 50
    item_id: uuid.UUID | None = None
    matches_item: uuid.UUID | None = None
    q: str | None = None
    kind: CollectionKind | None = None


@dataclass(kw_only=True, frozen=True)
class ListCollectionsResult:
    """A page of collection summaries."""

    items: list[CollectionSummary]


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
        collections = await self._page(query, scope)
        summaries = [
            await summarise(self._repos, self._items, c, scope) for c in collections
        ]
        logger.debug("collections listed", count=len(summaries))
        return ListCollectionsResult(items=summaries)

    async def _page(
        self, query: ListCollectionsQuery, scope: ContentFilter
    ) -> list[Collection]:
        """Return up to `query.limit` collections, keeping only those holding the item.

        Filtering happens while paging so a page is never short just because
        non-matching collections sat between matches.
        """
        kind = query.kind
        if query.matches_item is not None:
            if kind is CollectionKind.MANUAL:
                return []
            kind = CollectionKind.DYNAMIC
        if query.item_id is None and query.matches_item is None:
            return await self._repos.collections.list(
                scope=scope,
                after=query.after,
                limit=query.limit,
                q=query.q,
                kind=kind,
            )
        holding = (
            None
            if query.item_id is None
            else await self._repos.memberships.collection_ids_for(
                query.item_id, scope=scope
            )
        )
        found: list[Collection] = []
        after = query.after
        while len(found) < query.limit:
            batch = await self._repos.collections.list(
                scope=scope,
                after=after,
                limit=query.limit,
                q=query.q,
                kind=kind,
            )
            found.extend(
                [c for c in batch if await self._keeps(c, query, holding, scope)]
            )
            if len(batch) < query.limit:
                break
            after = batch[-1].id
        return found[: query.limit]

    async def _keeps(
        self,
        collection: Collection,
        query: ListCollectionsQuery,
        holding: set[uuid.UUID] | None,
        scope: ContentFilter,
    ) -> bool:
        """Whether the collection passes the `item_id` and `matches_item` filters."""
        if holding is not None and collection.id not in holding:
            return False
        if query.matches_item is None:
            return True
        if collection.definition is None:
            return False
        return await self._items.matches(
            collection.definition, scope, query.matches_item
        )
