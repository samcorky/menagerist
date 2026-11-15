import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.item_reach import load_in_order, reach_from_item
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.node import Node
from app.modules.graph.domain.reach import MAX_REACH_DEPTH
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetItemPathQuery:
    """Request for what holds an item, by one relationship, up to `depth` steps."""

    item_id: uuid.UUID
    relationship: str
    depth: int = MAX_REACH_DEPTH


class GetItemPath(QueryHandler[GraphRepos, GetItemPathQuery, list[Node]]):
    """List the items that hold an item, outermost first."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(self, query: GetItemPathQuery, actor: Actor) -> list[Node]:
        """Return the holders, farthest first, so the last one is the item's parent."""
        scope = self.scope(actor)
        reached = await reach_from_item(
            self._repos,
            self._guard,
            actor,
            scope=scope,
            item_id=query.item_id,
            relationship=query.relationship,
            direction="in",
            depth=query.depth,
        )
        # Nearest first from the walk; reversed, a breadcrumb reads root to parent.
        # Holders at the same distance (an item in two boxes) stay in id order.
        ordered = sorted(reached, key=lambda r: (-r.depth, r.node_id))
        nodes = await load_in_order(self._repos, scope, [r.node_id for r in ordered])
        logger.debug("item path listed", count=len(nodes))
        return nodes
