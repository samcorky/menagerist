import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.collections.domain.collection import Collection
from app.modules.collections.domain.errors import CollectionNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True, frozen=True)
class CollectionSummary:
    """A collection with the number of its members that are live items."""

    collection: Collection
    item_count: int


async def summarise(
    repos: CollectionsRepos, items: ItemLookup, collection: Collection
) -> CollectionSummary:
    """Count `collection`'s members that are still live items."""
    member_ids = await repos.memberships.item_ids(collection.id)
    live = await items.live_ids(list(member_ids))
    return CollectionSummary(collection=collection, item_count=len(live))


@dataclass(kw_only=True)
class GetCollectionQuery:
    """Request to fetch a single collection by id."""

    collection_id: uuid.UUID


class GetCollection(
    QueryHandler[CollectionsRepos, GetCollectionQuery, CollectionSummary]
):
    """Fetch a single collection with its live item count."""

    def __init__(self, repos: CollectionsRepos, items: ItemLookup) -> None:
        super().__init__(repos)
        self._items = items

    async def handle(
        self, query: GetCollectionQuery, actor: Actor
    ) -> CollectionSummary:
        """Return the collection, or raise `CollectionNotFoundError` if missing."""
        collection = await self._repos.collections.get(query.collection_id)
        if collection is None:
            raise CollectionNotFoundError(f"Collection {query.collection_id} not found")
        logger.debug("collection fetched", collection_id=collection.id)
        return await summarise(self._repos, self._items, collection)
