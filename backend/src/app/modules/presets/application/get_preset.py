import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import structlog

from app.modules.presets.domain.errors import PresetNotFoundError
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access import Access, Shared
from app.shared_kernel.guarded import GuardedQueryHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class GetPresetQuery:
    """Request to fetch a single preset by id."""

    preset_id: uuid.UUID


class GetPreset(GuardedQueryHandler[PresetRepos, GetPresetQuery, Preset]):
    """Fetch a single preset by id."""

    access: ClassVar[Access] = Shared()

    async def _handle(self, query: GetPresetQuery, actor: Actor) -> Preset:
        """Return the preset, or raise `PresetNotFoundError` if missing."""
        preset = await self._repos.presets.get(query.preset_id)
        if preset is None:
            raise PresetNotFoundError(f"Preset {query.preset_id} not found")
        logger.debug("preset fetched", preset_id=query.preset_id)
        return preset
