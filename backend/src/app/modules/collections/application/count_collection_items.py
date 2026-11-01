import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import CollectionKind
from app.modules.collections.domain.errors import CollectionNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.collections.ports.item_lookup import ItemLookup  # noqa: TC001
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CountCollectionItemsQuery:
    """Request for the exact number of items on a collection."""

    collection_id: uuid.UUID


class CountCollectionItems(
    QueryHandler[CollectionsRepos, CountCollectionItemsQuery, int]
):
    """Count a collection's items exactly, with no cap."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_READ)

    def __init__(
        self, repos: CollectionsRepos, guard: AccessGuard, items: ItemLookup
    ) -> None:
        super().__init__(repos, guard)
        self._items = items

    async def _handle(self, query: CountCollectionItemsQuery, actor: Actor) -> int:
        """Return the count, or raise `CollectionNotFoundError` if missing.

        A smart collection counts the items matching its definition in the
        caller's scope; a manual one counts its members that are live items.
        """
        scope = self.scope(actor)
        collection = await self._repos.collections.get(query.collection_id, scope=scope)
        if collection is None:
            raise CollectionNotFoundError(f"Collection {query.collection_id} not found")
        self._guard.assert_can_view(actor, collection.owner_id)
        if (
            collection.kind is CollectionKind.DYNAMIC
            and collection.definition is not None
        ):
            count, _ = await self._items.count_matching(
                collection.definition, scope, cap=None
            )
        else:
            member_ids = await self._repos.memberships.item_ids(
                collection.id, scope=scope
            )
            count = len(await self._items.live_ids(list(member_ids), scope))
        logger.debug("collection items counted", collection_id=collection.id)
        return count
