import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import EdgeTypeInUseError, EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteEdgeTypeCommand:
    """Request to soft-delete an edge type."""

    edge_type_id: uuid.UUID


class DeleteEdgeType(
    GuardedCommandHandler[GraphUnitOfWork, DeleteEdgeTypeCommand, None]
):
    """Soft-delete an edge type (administrators only).

    The in-use check spans every person's connections.
    """

    access: ClassVar[Access] = Requires(GraphPermission.DELETE_EDGE_TYPE)

    async def _handle(self, command: DeleteEdgeTypeCommand, actor: Actor) -> None:
        """Soft-delete the edge type or raise EdgeTypeNotFoundError."""
        async with self._uow as repos:
            edge_type = await repos.edge_types.get(command.edge_type_id)
            if edge_type is None:
                raise EdgeTypeNotFoundError(
                    f"Edge type {command.edge_type_id} not found"
                )
            # admin-wide: affects every user's content
            if await repos.edges.has_edges_of_type(
                str(edge_type.slug), scope=ContentFilter.everyone()
            ):
                raise EdgeTypeInUseError(
                    f"Edge type '{edge_type.slug}' "
                    + "is still used by one or more connections"
                )

            edge_type.soft_delete()
            await repos.edge_types.save(edge_type)
            await self._uow.commit()
        logger.info("edge type deleted", edge_type_id=command.edge_type_id)
