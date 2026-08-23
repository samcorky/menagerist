import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.graph.domain.errors import NodeNotFoundError

if TYPE_CHECKING:
    from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
    from app.shared_kernel.actor import Actor


@dataclass(kw_only=True)
class DeleteNodeCommand:
    """Request to soft-delete a node."""

    node_id: uuid.UUID


class DeleteNode:
    """Soft-delete an existing node."""

    def __init__(self, uow: GraphUnitOfWork) -> None:
        self._uow = uow

    async def handle(self, command: DeleteNodeCommand, actor: Actor) -> None:
        """Soft-delete the node identified by `command` and commit."""
        async with self._uow as repos:
            node = await repos.nodes.get(command.node_id)
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")

            node.soft_delete()

            await repos.nodes.save(node)
            await self._uow.commit()
