import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.batch_ids import check_batch_ids, unknown_items_error
from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.modules.graph.domain.node import Node
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeleteNodesCommand:
    """Request to soft-delete several nodes in one transaction."""

    node_ids: list[uuid.UUID]


class DeleteNodes(CommandHandler[GraphUnitOfWork, DeleteNodesCommand, None]):
    """Soft-delete several nodes, all or none."""

    access: ClassVar[Access] = Content(GraphPermission.ITEM_WRITE)

    async def _handle(self, command: DeleteNodesCommand, actor: Actor) -> None:
        """Soft-delete every node in `command` and commit once."""
        ids = check_batch_ids(command.node_ids)
        async with self._uow as repos:
            found: list[Node] = []
            missing: list[uuid.UUID] = []
            for node_id in ids:
                node = await repos.nodes.get(node_id, scope=self.scope(actor))
                if node is None:
                    missing.append(node_id)
                else:
                    found.append(node)
            if missing:
                raise unknown_items_error(missing)
            for node in found:
                self._guard.assert_can_delete(actor, node.owner_id)
            for node in found:
                node.soft_delete()
                await repos.nodes.save(node)
            await self._uow.commit()
        logger.info("nodes deleted", count=len(found))
