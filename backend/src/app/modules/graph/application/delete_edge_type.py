from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import EdgeTypeNotFoundError

if TYPE_CHECKING:
    import uuid

    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DeleteEdgeTypeCommand:
    """Request to soft-delete an edge type."""

    edge_type_id: "uuid.UUID"


class DeleteEdgeType:
    """Soft-delete an edge type."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: DeleteEdgeTypeCommand, actor: Actor) -> None:
        """Soft-delete the edge type or raise EdgeTypeNotFoundError."""
        async with self._uow as repos:
            edge_type = await repos.edge_types.get(command.edge_type_id)
            if edge_type is None:
                raise EdgeTypeNotFoundError(
                    f"Edge type {command.edge_type_id} not found"
                )
            edge_type.soft_delete()
            await repos.edge_types.save(edge_type)
            await self._uow.commit()
