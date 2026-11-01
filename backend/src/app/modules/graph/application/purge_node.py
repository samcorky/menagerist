import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, System
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class PurgeNodeCommand:
    """Request to hard-delete a node and its connections."""

    node_id: uuid.UUID


class PurgeNode(CommandHandler[GraphUnitOfWork, PurgeNodeCommand, None]):
    """Hard-delete an item and every connection touching it (for pack removal).

    Connections go first, as they reference the item. An unknown id is already
    gone, so a repeat is a no-op. Every connection touching the item goes, whoever
    owns the other end, so callers must first confirm the item has none of anyone
    else's (pack removal keeps such items).
    """

    access: ClassVar[Access] = System()

    async def _handle(self, command: PurgeNodeCommand, actor: Actor) -> None:
        """Delete the connections, then the node, and commit."""
        async with self._uow as repos:
            await repos.edges.purge_for_node(command.node_id)
            await repos.nodes.purge(command.node_id)
            await self._uow.commit()
        logger.info("node purged", node_id=command.node_id)
