import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.graph.application.permissions import GraphPermission
from app.modules.graph.domain.errors import EdgeTypeNotFoundError
from app.modules.graph.ports.unit_of_work import GraphUnitOfWork
from app.shared_kernel.access import Access, Requires
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.guarded import GuardedCommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_PAGE_SIZE = 100


@dataclass(kw_only=True)
class PurgeEdgeTypeAttributeCommand:
    """Request to permanently remove an attribute key from every edge of a type."""

    edge_type_id: uuid.UUID
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


class PurgeEdgeTypeAttribute(
    GuardedCommandHandler[GraphUnitOfWork, PurgeEdgeTypeAttributeCommand, None]
):
    """Remove an attribute key from every edge of a edge type (administrators only).

    The purge spans every person's connections.

    With `sub_key`, `key` names a group (array-of-objects) property and only
    `sub_key` is removed from each row, leaving the rest of the row and the
    array itself in place.

    Each edge is saved through the unit of work, so `updated_at` (and therefore
    the ETag) changes and a client holding a stale copy gets a 412 on its next
    save instead of writing the purged value back.
    """

    access: ClassVar[Access] = Requires(GraphPermission.PURGE_EDGE_TYPE_ATTRIBUTE)

    async def _handle(
        self, command: PurgeEdgeTypeAttributeCommand, actor: Actor
    ) -> None:
        """Purge the key; the count is logged, not returned (it spans every person)."""
        purged = 0
        async with self._uow as repos:
            edge_type = await repos.edge_types.get(command.edge_type_id)
            if edge_type is None:
                raise EdgeTypeNotFoundError(
                    f"EdgeType {command.edge_type_id} not found"
                )
            slug = str(edge_type.slug)
            after: uuid.UUID | None = None
            # admin-wide: affects every user's content
            while page := await repos.edges.list_with_attribute(
                slug,
                command.key,
                scope=ContentFilter.everyone(),
                sub_key=command.sub_key,
                after=after,
                limit=_PAGE_SIZE,
            ):
                for edge in page:
                    edge.update(
                        attributes=_purged_attributes(
                            edge.attributes, command.key, command.sub_key
                        )
                    )
                    await repos.edges.save(edge)
                purged += len(page)
                after = page[-1].id
            await self._uow.commit()
        logger.info(
            "edge type attribute purged",
            edge_type_id=command.edge_type_id,
            key=command.key,
            sub_key=command.sub_key,
            purged=purged,
        )
