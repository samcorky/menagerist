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
class PurgeEdgeCommand:
    """Request to hard-delete a connection."""

    edge_id: uuid.UUID


class PurgeEdge(CommandHandler[GraphUnitOfWork, PurgeEdgeCommand, None]):
    """Hard-delete a connection (for pack removal); an unknown id is a no-op."""

    access: ClassVar[Access] = System()

    async def _handle(self, command: PurgeEdgeCommand, actor: Actor) -> None:
        """Delete the connection and commit."""
        async with self._uow as repos:
            await repos.edges.purge(command.edge_id)
            await self._uow.commit()
        logger.info("edge purged", edge_id=command.edge_id)
