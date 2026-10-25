import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.collections.application.permissions import CollectionPermission
from app.modules.collections.domain.collection import Collection
from app.modules.collections.ports.unit_of_work import CollectionsRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListDeletedCollectionsQuery:
    """Request for a page of deleted collections, newest deleted first."""

    after: uuid.UUID | None = None
    limit: int = 50


@dataclass(kw_only=True, frozen=True)
class ListDeletedCollectionsResult:
    """A page of deleted collections and how many are in Recently deleted."""

    items: list[Collection]
    total: int


class ListDeletedCollections(
    QueryHandler[
        CollectionsRepos, ListDeletedCollectionsQuery, ListDeletedCollectionsResult
    ]
):
    """List the caller's deleted collections, newest deleted first."""

    access: ClassVar[Access] = Content(CollectionPermission.COLLECTION_READ)

    async def _handle(
        self, query: ListDeletedCollectionsQuery, actor: Actor
    ) -> ListDeletedCollectionsResult:
        """Return a page of deleted collections after `query.after`."""
        scope = self.scope(actor)
        items = await self._repos.collections.list_deleted(
            scope=scope, after=query.after, limit=query.limit
        )
        total = await self._repos.collections.count_deleted(scope=scope)
        logger.debug("deleted collections listed", count=len(items), total=total)
        return ListDeletedCollectionsResult(items=items, total=total)
