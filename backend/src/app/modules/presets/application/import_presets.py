from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import structlog

from app.modules.presets.application.pack import (
    check_pack_envelope,
    check_pack_item,
    content_hash,
)
from app.modules.presets.application.preset_definitions import check_definition
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.shared_kernel.cqrs import CommandHandler

if TYPE_CHECKING:
    import uuid

    from app.modules.presets.ports.preset_repository import PresetRepository
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_PAGE_SIZE = 100


@dataclass(kw_only=True)
class ImportPresetsCommand:
    """A pack of presets to import. Items get new ids; nothing is overwritten."""

    pack_format: str
    pack_version: int
    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(kw_only=True)
class ImportPresetsResult:
    """How many presets a pack created and how many were skipped as repeats."""

    created: int
    skipped: int


class ImportPresets(
    CommandHandler[PresetUnitOfWork, ImportPresetsCommand, ImportPresetsResult]
):
    """Import a pack, skipping any preset whose content already exists.

    The whole pack is checked before anything is stored, so one bad item rejects it all.
    """

    async def handle(
        self, command: ImportPresetsCommand, actor: Actor
    ) -> ImportPresetsResult:
        """Validate `command` and store the presets it holds that are new."""
        check_pack_envelope(command.pack_format, command.pack_version, command.items)
        for item in command.items:
            check_pack_item(item)
            check_definition(item["kind"], item["definition"])

        async with self._uow as repos:
            seen = await _existing_hashes(repos.presets)
            created = 0
            skipped = 0
            for item in command.items:
                digest = content_hash(item["kind"], item["label"], item["definition"])
                if digest in seen:
                    skipped += 1
                    continue
                seen.add(digest)
                await repos.presets.add(
                    Preset.create(
                        kind=item["kind"],
                        label=item["label"],
                        description=item.get("description"),
                        definition=item["definition"],
                    )
                )
                created += 1
            await self._uow.commit()

        logger.info("presets imported", created=created, skipped=skipped)
        return ImportPresetsResult(created=created, skipped=skipped)


async def _existing_hashes(repos: PresetRepository) -> set[str]:
    """Return the content hash of every live preset, read a page at a time."""
    hashes: set[str] = set()
    after: uuid.UUID | None = None
    while True:
        page = await repos.list(after=after, limit=_PAGE_SIZE)
        for preset in page:
            hashes.add(content_hash(preset.kind, preset.label, preset.definition))
        if len(page) < _PAGE_SIZE:
            return hashes
        after = page[-1].id
