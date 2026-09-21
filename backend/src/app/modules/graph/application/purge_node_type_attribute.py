import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.graph.domain.errors import NodeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_PAGE_SIZE = 100


@dataclass(kw_only=True)
class PurgeNodeTypeAttributeCommand:
    """Request to permanently remove an attribute key from every node of a type."""

    node_type_id: uuid.UUID
    key: str


class PurgeNodeTypeAttribute(
    CommandHandler[GraphUnitOfWork, PurgeNodeTypeAttributeCommand, int]
):
    """Remove an attribute key from every node of a node type.

    Each node is saved through the unit of work, so `updated_at` (and therefore
    the ETag) changes and a client holding a stale copy gets a 412 on its next
    save instead of writing the purged value back.
    """

    async def handle(self, command: PurgeNodeTypeAttributeCommand, actor: Actor) -> int:
        """Purge the key and return how many nodes held it."""
        purged = 0
        async with self._uow as repos:
            node_type = await repos.node_types.get(command.node_type_id)
            if node_type is None:
                raise NodeTypeNotFoundError(
                    f"NodeType {command.node_type_id} not found"
                )
            slug = str(node_type.slug)
            after: uuid.UUID | None = None
            while page := await repos.nodes.list_with_attribute(
                slug, command.key, after=after, limit=_PAGE_SIZE
            ):
                for node in page:
                    node.update(
                        attributes={
                            k: v for k, v in node.attributes.items() if k != command.key
                        }
                    )
                    await repos.nodes.save(node)
                purged += len(page)
                after = page[-1].id
            await self._uow.commit()
        logger.info(
            "node type attribute purged",
            node_type_id=command.node_type_id,
            key=command.key,
            purged=purged,
        )
        return purged
