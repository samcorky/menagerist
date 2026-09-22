import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.presets.application.preset_definitions import check_definition
from app.modules.presets.domain.errors import PresetNotFoundError
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class UpdatePresetCommand:
    """Request to update a preset's editable fields.

    Setting `definition` bumps `version`, so types that copied an earlier
    version can offer "update available".
    """

    preset_id: uuid.UUID
    label: str | None = field(default=None)
    description: str | None = field(default=None)
    definition: dict[str, Any] | None = field(default=None)


class UpdatePreset(CommandHandler[PresetUnitOfWork, UpdatePresetCommand, Preset]):
    """Update an existing preset's editable fields.

    :raises BuiltinPresetError: a built-in preset cannot be edited.
    """

    async def handle(self, command: UpdatePresetCommand, actor: Actor) -> Preset:
        """Apply `command`'s changes to the preset and commit."""
        async with self._uow as repos:
            preset = await repos.presets.get(command.preset_id)
            if preset is None:
                raise PresetNotFoundError(f"Preset {command.preset_id} not found")

            if command.definition is not None:
                check_definition(preset.kind, command.definition)

            preset.update(
                label=command.label,
                description=command.description,
                definition=command.definition,
            )

            await repos.presets.save(preset)
            await self._uow.commit()
        logger.info("preset updated", preset_id=command.preset_id)
        return preset
