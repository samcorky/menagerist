from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.presets.application.permissions import PresetPermission
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access import Access, Content
from app.shared_kernel.cqrs import QueryHandler
from app.shared_kernel.paging import Cursor, Page, PageRequest, SortOrder

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


class PresetSort(StrEnum):
    """What a list of saved fields can be sorted by: fields of the response."""

    LABEL = "label"
    KIND = "kind"
    CREATED_AT = "created_at"
    UPDATED_AT = "updated_at"


@dataclass(kw_only=True)
class ListPresetsQuery:
    """Request to list presets, optionally filtered by kind or a label search."""

    after: Cursor | None = field(default=None)
    limit: int = field(default=50)
    sort: PresetSort | None = field(default=None)
    order: SortOrder = field(default=SortOrder.ASC)
    kind: str | None = field(default=None)
    q: str | None = field(default=None)


class ListPresets(QueryHandler[PresetRepos, ListPresetsQuery, Page[Preset]]):
    """List presets one page at a time, by id unless `sort` says otherwise."""

    access: ClassVar[Access] = Content(PresetPermission.PRESET_READ)

    async def _handle(self, query: ListPresetsQuery, actor: Actor) -> Page[Preset]:
        """Return the page of presets matching `query`."""
        page = await self._repos.presets.list(
            scope=self.scope(actor),
            page=PageRequest(
                after=query.after,
                limit=query.limit,
                sort=None if query.sort is None else query.sort.value,
                order=query.order,
            ),
            kind=query.kind,
            q=query.q,
        )
        logger.debug("presets listed", count=len(page.items), kind=query.kind)
        return page
