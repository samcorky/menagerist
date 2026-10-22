"""List the fields individual items carry in their own overlay."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.graph.domain.query import ItemFieldUse
from app.modules.graph.ports.unit_of_work import GraphRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

MAX_ITEM_FIELDS = 200


@dataclass(frozen=True)
class ListItemFieldsQuery:
    """Request for the per-item fields in use."""


class ListItemFields(
    GuardedQueryHandler[GraphRepos, ListItemFieldsQuery, list[ItemFieldUse]]
):
    """List per-item fields the caller can filter on, most used first.

    Fields come from the `extra_schema` overlays of the caller's items. Only
    fields with an explicit, filterable `x-menagerist.kind` that are not
    archived are listed (inferred-kind fields are omitted). A field's `label` is
    the JSON Schema `title` the schema editor writes for it: the most common
    title among items sharing the key and kind, falling back to the key.
    """

    access: ClassVar[Access] = Content()

    async def _handle(
        self, query: ListItemFieldsQuery, actor: Actor
    ) -> list[ItemFieldUse]:
        """Return at most `MAX_ITEM_FIELDS` fields, by count then key."""
        fields = await self._repos.nodes.item_fields(
            scope=self.scope(actor), limit=MAX_ITEM_FIELDS
        )
        logger.debug("item fields listed", count=len(fields))
        return fields
