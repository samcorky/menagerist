import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.get_collection import (
    CollectionSummary,
    summarise,
)

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
    """

    after: uuid.UUID | None = None
    limit: int = 50
    item_id: uuid.UUID | None = None
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

    access: ClassVar[Access] = Content()

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
        if query.item_id is None:
            return await self._repos.collections.list(
                scope=scope,
                after=query.after,
                limit=query.limit,
                q=query.q,
                kind=query.kind,
            )
        holding = await self._repos.memberships.collection_ids_for(
            query.item_id, scope=scope
        )
        found: list[Collection] = []
        after = query.after
        while len(found) < query.limit:
            batch = await self._repos.collections.list(
                scope=scope,
                after=after,
                limit=query.limit,
                q=query.q,
                kind=query.kind,
            )
            found.extend(c for c in batch if c.id in holding)
            if len(batch) < query.limit:
                break
            after = batch[-1].id
        return found[: query.limit]
