import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import Collection, CollectionKind
from app.modules.collections.domain.definition_warning import DefinitionWarning
from app.modules.collections.domain.errors import (
    CollectionNotFoundError,
    InvalidDefinitionError,
)

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.definition_checker import (
    DefinitionChecker,  # noqa: TC001
)

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.content_filter import ContentFilter  # noqa: TC001
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

# Matches the search endpoint's total cap.
ITEM_COUNT_CAP = 1000


@dataclass(kw_only=True, frozen=True)
class CollectionSummary:
    """A collection with the number of its members that are live items.

    For a smart collection the count stops at `ITEM_COUNT_CAP`, and
    `item_count_capped` says so. `warnings` lists the parts of its definition
    that no longer apply; only `GetCollection` fills them.
    """

    collection: Collection
    item_count: int
    item_count_capped: bool = False
    warnings: tuple[DefinitionWarning, ...] = ()


async def summarise(
    repos: CollectionsRepos,
    items: ItemLookup,
    collection: Collection,
    scope: ContentFilter,
) -> CollectionSummary:
    """Count `collection`'s members that are live items visible in `scope`."""
    if collection.kind is CollectionKind.DYNAMIC and collection.definition is not None:
        count, capped = await items.count_matching(
            collection.definition, scope, cap=ITEM_COUNT_CAP
        )
        return CollectionSummary(
            collection=collection, item_count=count, item_count_capped=capped
        )
    member_ids = await repos.memberships.item_ids(collection.id, scope=scope)
    live = await items.live_ids(list(member_ids), scope)
    return CollectionSummary(collection=collection, item_count=len(live))


@dataclass(kw_only=True)
class GetCollectionQuery:
    """Request to fetch a single collection by id."""

    collection_id: uuid.UUID


class GetCollection(
    QueryHandler[CollectionsRepos, GetCollectionQuery, CollectionSummary]
):
    """Fetch a single collection with its live item count."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_READ)

    def __init__(
        self,
        repos: CollectionsRepos,
        guard: AccessGuard,
        items: ItemLookup,
        checker: DefinitionChecker,
    ) -> None:
        super().__init__(repos, guard)
        self._items = items
        self._checker = checker

    async def _handle(
        self, query: GetCollectionQuery, actor: Actor
    ) -> CollectionSummary:
        """Return the collection, or raise `CollectionNotFoundError` if missing."""
        scope = self.scope(actor)
        collection = await self._repos.collections.get(query.collection_id, scope=scope)
        if collection is None:
            raise CollectionNotFoundError(f"Collection {query.collection_id} not found")
        self._guard.assert_can_view(actor, collection.owner_id)
        logger.debug("collection fetched", collection_id=collection.id)
        summary = await summarise(self._repos, self._items, collection, scope)
        if (
            collection.kind is not CollectionKind.DYNAMIC
            or collection.definition is None
        ):
            return summary
        try:
            warnings = await self._checker.check(collection.definition, scope)
        except InvalidDefinitionError as exc:
            # No longer valid (for example an item type changed): matches nothing.
            warnings = [DefinitionWarning(path=exc.path, message=str(exc))]
        return replace(summary, warnings=tuple(warnings))
