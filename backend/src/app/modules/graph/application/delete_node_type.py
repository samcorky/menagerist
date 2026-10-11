import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access_scope import AccessScope
from app.shared_kernel.cqrs import AuthorisedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteNodeTypeCommand:
    """Request to soft-delete a node type."""

    node_type_id: uuid.UUID


class DeleteNodeType(
    AuthorisedCommandHandler[
        GraphUnitOfWork, DeleteNodeTypeCommand, None, GraphPermission
    ]
):
    """Soft-delete an existing node type (administrators only).

    Clearing the type spans every person's items.
    """

    required_permission = GraphPermission.DELETE_NODE_TYPE

    async def _handle(self, command: DeleteNodeTypeCommand, actor: Actor) -> None:
        """Soft-delete the node type identified by `command` and commit."""
        async with self._uow as repos:
            node_type = await repos.node_types.get(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )

            node_type.soft_delete()

            await repos.node_types.save(node_type)
            # admin-wide: affects every user's content
            await repos.nodes.clear_type(
                str(node_type.slug), scope=AccessScope.everyone()
            )
            await self._uow.commit()
        logger.info("node type deleted", node_type_id=command.node_type_id)
