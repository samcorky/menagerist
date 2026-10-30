"""Count the caller's items per item type."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.query import TypeCount
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(frozen=True)
class CountNodeTypesQuery:
    """Request for the item types the caller's items use, with counts."""


class CountNodeTypes(QueryHandler[GraphRepos, CountNodeTypesQuery, list[TypeCount]]):
    """Count the caller's live items per item type.

    Only types with at least one of the caller's items appear, so a shared
    catalogue of item types never inflates the numbers. Untyped items are one
    row with no type. Biggest first, then by type, the untyped row last on a tie.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_READ)

    async def _handle(
        self, query: CountNodeTypesQuery, actor: Actor
    ) -> list[TypeCount]:
        """Return one row per type in use in the actor's scope."""
        rows = await self._repos.nodes.count_by_type(scope=self.scope(actor))
        logger.debug("node types counted", types=len(rows))
        return rows
