import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import NodeNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.graph.ports.item_dependents import ItemDependents  # noqa: TC001
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.access_guard import AccessGuard
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PurgeDeletedNodeCommand:
    """Request to permanently delete an item that is already in Recently deleted."""

    node_id: uuid.UUID


class PurgeDeletedNode(CommandHandler[GraphUnitOfWork, PurgeDeletedNodeCommand, None]):
    """Permanently delete one of the caller's deleted items.

    A live item, an unknown id and another person's item are all not found.
    Memberships and attachments go first, then the connections (live or
    deleted) and the item itself, so an interrupted run leaves the item in
    Recently deleted to be purged again.
    """

    access: ClassVar[Access] = Content(GraphPermission.ITEM_PURGE)

    def __init__(
        self, uow: GraphUnitOfWork, guard: AccessGuard, dependents: ItemDependents
    ) -> None:
        super().__init__(uow, guard)
        self._dependents = dependents

    async def _handle(self, command: PurgeDeletedNodeCommand, actor: Actor) -> None:
        """Purge the item and everything that hangs off it."""
        async with self._uow as repos:
            node = await repos.nodes.get_deleted(
                command.node_id, scope=self.scope(actor)
            )
            if node is None:
                raise NodeNotFoundError(f"Node {command.node_id} not found")
            self._guard.assert_can_delete(actor, node.owner_id)
            await self._dependents.purge_for_item(node.id)
            await repos.edges.purge_for_node(node.id)
            await repos.nodes.purge(node.id)
            await self._uow.commit()
        logger.info("deleted node purged", node_id=command.node_id)
