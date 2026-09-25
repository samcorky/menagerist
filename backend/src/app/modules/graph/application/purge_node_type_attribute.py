import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

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
    sub_key: str | None = None


def _purged_attributes(
    attributes: dict[str, Any], key: str, sub_key: str | None
) -> dict[str, Any]:
    """`attributes` with `key`, or `sub_key` from each row of `key`, removed."""
    if sub_key is None:
        return {k: v for k, v in attributes.items() if k != key}
    # `list_with_attribute(..., sub_key=...)` only returns nodes/edges where `key`
    # is already an array holding a matching dict row, so `rows` is always a list here.
    rows = attributes[key]
    purged_rows = [
        {k: v for k, v in row.items() if k != sub_key} if isinstance(row, dict) else row
        for row in rows
    ]
    return {**attributes, key: purged_rows}


class PurgeNodeTypeAttribute(
    CommandHandler[GraphUnitOfWork, PurgeNodeTypeAttributeCommand, int]
):
    """Remove an attribute key from every node of a node type.

    With `sub_key`, `key` names a group (array-of-objects) property and only
    `sub_key` is removed from each row, leaving the rest of the row and the
    array itself in place.

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
                slug,
                command.key,
                sub_key=command.sub_key,
                after=after,
                limit=_PAGE_SIZE,
            ):
                for node in page:
                    node.update(
                        attributes=_purged_attributes(
                            node.attributes, command.key, command.sub_key
                        )
                    )
                    await repos.nodes.save(node)
                purged += len(page)
                after = page[-1].id
            await self._uow.commit()
        logger.info(
            "node type attribute purged",
            node_type_id=command.node_type_id,
            key=command.key,
            sub_key=command.sub_key,
            purged=purged,
        )
        return purged
