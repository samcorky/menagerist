import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListDeletedNodesQuery:
    """Request for a page of deleted items, newest deleted first."""

    after: uuid.UUID | None = None
    limit: int = 50


@dataclass(frozen=True)
class ListDeletedNodesResult:
    """A page of deleted items and how many are in Recently deleted."""

    items: list[Node]
    total: int


class ListDeletedNodes(
    QueryHandler[GraphRepos, ListDeletedNodesQuery, ListDeletedNodesResult]
):
    """List the caller's deleted items, newest deleted first."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(
        self, query: ListDeletedNodesQuery, actor: Actor
    ) -> ListDeletedNodesResult:
        """Return a page of deleted items after `query.after`."""
        scope = self.scope(actor)
        items = await self._repos.nodes.list_deleted(
            scope=scope, after=query.after, limit=query.limit
        )
        total = await self._repos.nodes.count_deleted(scope=scope)
        logger.debug("deleted nodes listed", count=len(items), total=total)
        return ListDeletedNodesResult(items=items, total=total)
