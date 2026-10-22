import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.domain.errors import EdgeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteEdgeCommand:
    """Request to soft-delete an edge."""

    edge_id: uuid.UUID


class DeleteEdge(CommandHandler[GraphUnitOfWork, DeleteEdgeCommand, None]):
    """Soft-delete an existing edge."""

    access: ClassVar[Access] = Content()

    async def _handle(self, command: DeleteEdgeCommand, actor: Actor) -> None:
        """Soft-delete the edge identified by `command` and commit."""
        async with self._uow as repos:
            edge = await repos.edges.get(command.edge_id, scope=self.scope(actor))
            if edge is None:
                raise EdgeNotFoundError(f"Edge {command.edge_id} not found")
            self._guard.assert_can_delete(actor, edge.owner_id)

            edge.soft_delete()

            await repos.edges.save(edge)
            await self._uow.commit()
        logger.info("edge deleted", edge_id=command.edge_id)
