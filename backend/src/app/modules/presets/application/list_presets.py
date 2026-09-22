import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ListPresetsQuery:
    """Request to list presets, optionally filtered by kind or a label search."""

    after: uuid.UUID | None = field(default=None)
    limit: int = field(default=50)
    kind: str | None = field(default=None)
    q: str | None = field(default=None)


class ListPresets(QueryHandler[PresetRepos, ListPresetsQuery, list[Preset]]):
    """List presets, paginated by id."""

    async def handle(self, query: ListPresetsQuery, actor: Actor) -> list[Preset]:
        """Return presets matching `query`."""
        presets = await self._repos.presets.list(
            after=query.after, limit=query.limit, kind=query.kind, q=query.q
        )
        logger.debug("presets listed", count=len(presets), kind=query.kind)
        return presets
