import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import EdgeTypeInUseError, EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DeleteEdgeTypeCommand:
    """Request to soft-delete an edge type."""

    edge_type_id: uuid.UUID


class DeleteEdgeType(CommandHandler[GraphUnitOfWork, DeleteEdgeTypeCommand, None]):
    """Soft-delete an edge type."""

    async def handle(self, command: DeleteEdgeTypeCommand, actor: Actor) -> None:
        """Soft-delete the edge type or raise EdgeTypeNotFoundError."""
        async with self._uow as repos:
            edge_type = await repos.edge_types.get(command.edge_type_id)
            if edge_type is None:
                raise EdgeTypeNotFoundError(
                    f"Edge type {command.edge_type_id} not found"
                )
            if await repos.edges.has_edges_of_type(str(edge_type.slug)):
                raise EdgeTypeInUseError(
                    f"Edge type '{edge_type.slug}' "
                    + "is still used by one or more connections"
                )

            edge_type.soft_delete()
            await repos.edge_types.save(edge_type)
            await self._uow.commit()
