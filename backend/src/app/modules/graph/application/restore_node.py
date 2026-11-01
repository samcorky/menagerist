import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import NodeNotFoundError, NodeTypeDeletedError
from app.modules.graph.domain.node import Node
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class RestoreNodeCommand:
    """Request to bring a deleted item back."""

    node_id: uuid.UUID


class RestoreNode(CommandHandler[GraphUnitOfWork, RestoreNodeCommand, Node]):
    """Clear an item's deletion mark and nothing else.

    Its connections and collection memberships were never touched by the delete,
    so they reappear; a connection deleted on its own stays deleted.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_WRITE)

    async def _handle(self, command: RestoreNodeCommand, actor: Actor) -> Node:
        """Restore the item and commit.

        Raises:
            NodeNotFoundError: If the item is not in the caller's Recently deleted list.
            NodeTypeDeletedError: If the item's type has been deleted since.
        """
        async with self._uow as repos:
            node = await repos.nodes.get_deleted(
                command.node_id, scope=self.scope(actor)
            )
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")
            self._guard.assert_can_delete(actor, node.owner_id)
            if (
                node.type is not None
                and await repos.node_types.get_by_slug(node.type) is None
            ):
                raise NodeTypeDeletedError(
                    f"The item type '{node.type}' has been deleted. "
                    + "Create an item type with that slug, then try again."
                )
            node.restore()
            await repos.nodes.save(node)
            await self._uow.commit()
        logger.info("node restored", node_id=command.node_id)
        return node
