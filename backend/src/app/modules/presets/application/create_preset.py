from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.presets.application.preset_definitions import check_definition
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()


@dataclass(kw_only=True)
class CreatePresetCommand:
    """Request to save a new preset."""

    kind: str
    label: str
    description: str | None = field(default=None)
    definition: dict[str, Any] = field(default_factory=dict)


class CreatePreset(CommandHandler[PresetUnitOfWork, CreatePresetCommand, Preset]):
    """Create and persist a new preset."""

    async def handle(self, command: CreatePresetCommand, actor: Actor) -> Preset:
        """Create a preset from `command` and commit it."""
        check_definition(command.kind, command.definition)
        preset = Preset.create(
            kind=command.kind,
            label=command.label,
            description=command.description,
            definition=command.definition,
        )
        async with self._uow as repos:
            await repos.presets.add(preset)
            await self._uow.commit()
        logger.info("preset created", preset_id=preset.id, kind=preset.kind)
        return preset
