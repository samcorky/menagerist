import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import NodeTypeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DeleteNodeTypeCommand:
    """Request to soft-delete a node type."""

    node_type_id: uuid.UUID


class DeleteNodeType:
    """Soft-delete an existing node type."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: DeleteNodeTypeCommand, actor: Actor) -> None:
        """Soft-delete the node type identified by `command` and commit."""
        async with self._uow as repos:
            node_type = await repos.node_types.get(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )

            node_type.soft_delete()

            await repos.node_types.save(node_type)
            await self._uow.commit()
