import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.item_reach import load_in_order, reach_from_item
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListItemContentsQuery:
    """Request for what an item holds, by one relationship, up to `depth` steps."""

    item_id: uuid.UUID
    relationship: str
    depth: int = 1
    after: uuid.UUID | None = None
    limit: int = 50


@dataclass(frozen=True, kw_only=True)
class ContentsEntry:
    """An item found inside another, and how many steps in it sits."""

    node: Node
    depth: int


class ListItemContents(
    QueryHandler[GraphRepos, ListItemContentsQuery, list[ContentsEntry]]
):
    """List the items an item holds, nearest first, a page at a time."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(
        self, query: ListItemContentsQuery, actor: Actor
    ) -> list[ContentsEntry]:
        """Return a page after `query.after` in (depth, id) order."""
        scope = self.scope(actor)
        reached = await reach_from_item(
            self._repos,
            self._guard,
            actor,
            scope=scope,
            item_id=query.item_id,
            relationship=query.relationship,
            toward="held",
            depth=query.depth,
        )
        ids = [r.node_id for r in reached]
        start = 0
        if query.after is not None:
            # The order is (depth, id), so the cursor is a position, not an id range.
            start = ids.index(query.after) + 1 if query.after in ids else len(ids)
        page = reached[start : start + query.limit]
        nodes = await load_in_order(self._repos, scope, [r.node_id for r in page])
        depths = {r.node_id: r.depth for r in page}
        logger.debug("item contents listed", count=len(nodes))
        return [ContentsEntry(node=n, depth=depths[n.id]) for n in nodes]
