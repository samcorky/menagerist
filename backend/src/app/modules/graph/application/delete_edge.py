import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import EdgeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DeleteEdgeCommand:
    """Request to soft-delete an edge."""

    edge_id: uuid.UUID


class DeleteEdge:
    """Soft-delete an existing edge."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: DeleteEdgeCommand, actor: Actor) -> None:
        """Soft-delete the edge identified by `command` and commit."""
        async with self._uow as repos:
            edge = await repos.edges.get(command.edge_id)
            if edge is None:
                raise EdgeNotFoundError(f"Edge {command.edge_id} not found")

            edge.soft_delete()

            await repos.edges.save(edge)
            await self._uow.commit()
