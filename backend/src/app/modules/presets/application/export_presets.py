import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import structlog

from app.modules.presets.application.pack import MAX_PACK_ITEMS
from app.modules.presets.domain.errors import (
    InvalidPresetDefinitionError,
    PresetNotFoundError,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.cqrs import QueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class ExportPresetsQuery:
    """Request to export the presets with `ids` as a pack."""

    ids: list[uuid.UUID] = field(default_factory=list)


class ExportPresets(QueryHandler[PresetRepos, ExportPresetsQuery, list[Preset]]):
    """Fetch the presets to put in a pack, in the order requested."""

    async def handle(self, query: ExportPresetsQuery, actor: Actor) -> list[Preset]:
        """Return the presets for `query.ids`, or raise on the first missing one.

        :raises PresetNotFoundError: an id does not resolve to a live preset.
        :raises ValidationError: more ids than a pack may hold.
        """
        if len(query.ids) > MAX_PACK_ITEMS:
            raise InvalidPresetDefinitionError(
                f"a pack may hold at most {MAX_PACK_ITEMS} presets"
            )
        presets: list[Preset] = []
        for preset_id in query.ids:
            preset = await self._repos.presets.get(preset_id)
            if preset is None:
                raise PresetNotFoundError(f"Preset {preset_id} not found")
            presets.append(preset)
        logger.debug("presets exported", count=len(presets))
        return presets
