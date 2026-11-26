import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, ClassVar

import structlog

from app.modules.presets.application.pack import check_presets
from app.modules.presets.application.permissions import PresetPermission
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetUnitOfWork
from app.modules.transfer.application.content_hash import preset_key
from app.shared_kernel.access import Access, Content
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.cqrs import CommandHandler
from app.shared_kernel.paging import PageRequest

if TYPE_CHECKING:
    from app.modules.presets.ports.preset_repository import PresetRepository
    from app.shared_kernel.actor import Actor

logger = structlog.get_logger()

_PAGE_SIZE = 100


@dataclass(kw_only=True)
class ImportPresetsCommand:
    """Presets to import. They get new ids; nothing is overwritten."""

    items: list[dict[str, Any]] = field(default_factory=list)


@dataclass(kw_only=True)
class ImportedPreset:
    """The preset an imported item resolved to, and whether it was newly created."""

    id: uuid.UUID
    created: bool


@dataclass(kw_only=True)
class ImportPresetsResult:
    """What an import did: counts, plus the preset for each item, in order."""

    created: int
    skipped: int
    items: list[ImportedPreset] = field(default_factory=list)


class ImportPresets(
    CommandHandler[PresetUnitOfWork, ImportPresetsCommand, ImportPresetsResult]
):
    """Import presets, skipping any whose content the person already has.

    All of them are checked before anything is stored, so one bad item rejects them
    all. Files reach this through the `transfer` preset target.
    """

    access: ClassVar[Access] = Content(PresetPermission.PRESET_WRITE)

    async def _handle(
        self, command: ImportPresetsCommand, actor: Actor
    ) -> ImportPresetsResult:
        """Validate `command` and store the presets it holds that are new."""
        check_presets(command.items)

        async with self._uow as repos:
            seen = await existing_hashes(repos.presets, ContentFilter.of(actor.id))
            items: list[ImportedPreset] = []
            for item in command.items:
                digest = preset_key(item["kind"], item["label"], item["definition"])
                if digest in seen:
                    items.append(ImportedPreset(id=seen[digest], created=False))
                    continue
                preset = Preset.create(
                    owner_id=actor.id,
                    kind=item["kind"],
                    label=item["label"],
                    description=item.get("description"),
                    definition=item["definition"],
                )
                await repos.presets.add(preset)
                seen[digest] = preset.id
                items.append(ImportedPreset(id=preset.id, created=True))
            await self._uow.commit()

        created = sum(1 for i in items if i.created)
        skipped = len(items) - created
        logger.info("presets imported", created=created, skipped=skipped)
        return ImportPresetsResult(created=created, skipped=skipped, items=items)


async def existing_hashes(
    repos: PresetRepository, scope: ContentFilter
) -> dict[str, uuid.UUID]:
    """Map the content hash of every live preset in `scope` to its id."""
    hashes: dict[str, uuid.UUID] = {}
    request = PageRequest(limit=_PAGE_SIZE)
    while True:
        page = await repos.list(scope=scope, page=request)
        for preset in page.items:
            digest = preset_key(preset.kind, preset.label, preset.definition)
            hashes[digest] = preset.id
        if page.next is None:
            return hashes
        request = PageRequest(after=page.next, limit=_PAGE_SIZE)
