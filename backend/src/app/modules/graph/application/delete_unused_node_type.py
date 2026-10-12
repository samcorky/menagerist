import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import NodeTypeInUseError, NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.cqrs import AuthorisedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteUnusedNodeTypeCommand:
    """Request to soft-delete a node type only if no item uses it."""

    node_type_id: uuid.UUID


class DeleteUnusedNodeType(
    AuthorisedCommandHandler[
        GraphUnitOfWork, DeleteUnusedNodeTypeCommand, None, GraphPermission
    ]
):
    """Soft-delete an item type that nothing uses (for example-pack removal).

    The in-use check spans every person's items and shares one transaction with
    the delete. The type row is locked first, and item writes hold it too, so an
    item cannot be added to the type between the check and the delete. Unlike
    `DeleteNodeType` this never clears the type on anyone's items.
    """

    required_permission = GraphPermission.DELETE_NODE_TYPE

    async def _handle(self, command: DeleteUnusedNodeTypeCommand, actor: Actor) -> None:
        """Delete the type or raise `NodeTypeInUseError` / `NodeTypeNotFoundError`."""
        async with self._uow as repos:
            node_type = await repos.node_types.get_for_removal(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )
            # all-users check: shared structure
            in_use = await repos.nodes.list(
                scope=AccessScope.everyone(),
                after=None,
                limit=1,
                type=str(node_type.slug),
            )
            if in_use:
                raise NodeTypeInUseError(
                    f"Item type '{node_type.slug}' is still used by one or more items"
                )
            node_type.soft_delete()
            await repos.node_types.save(node_type)
            await self._uow.commit()
        logger.info("unused node type deleted", node_type_id=command.node_type_id)
