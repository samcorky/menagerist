import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

from app.modules.presets.domain.errors import PresetInUseError, PresetNotFoundError

# Needed at runtime: the CQRS signature test evaluates __init__ annotations.
from app.modules.presets.ports.preset_usage import PresetUsage  # noqa: TC001
from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class DeletePresetCommand:
    """Request to soft-delete a preset."""

    preset_id: uuid.UUID


class DeletePreset(CommandHandler[PresetUnitOfWork, DeletePresetCommand, None]):
    """Soft-delete an existing preset.

    :raises BuiltinPresetError: a built-in preset cannot be deleted.
    :raises PresetInUseError: an item type still references the preset.
    """

    def __init__(self, uow: PresetUnitOfWork, usage: PresetUsage | None = None) -> None:
        super().__init__(uow)
        self._usage = usage

    async def handle(self, command: DeletePresetCommand, actor: Actor) -> None:
        """Soft-delete the preset identified by `command` and commit."""
        async with self._uow as repos:
            preset = await repos.presets.get(command.preset_id)
            if preset is None:
                raise PresetNotFoundError(f"Preset {command.preset_id} not found")

            if self._usage is not None:
                types = await self._usage.types_using(command.preset_id)
                if types:
                    raise PresetInUseError(
                        f"Used by {', '.join(types)}. Remove it from those types first."
                    )

            preset.soft_delete()

            await repos.presets.save(preset)
            await self._uow.commit()
        logger.info("preset deleted", preset_id=command.preset_id)
