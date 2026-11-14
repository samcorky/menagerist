"""Every shipped entry is something the app will actually accept."""

import json

from app.modules.catalogue.adapters.platform.file_entry_catalogue import (
    FileEntryCatalogue,
)
from app.modules.presets.application.pack import check_pack_item
from app.modules.presets.application.preset_definitions import check_definition
from app.shared_kernel.slug import slugify


async def test_every_preset_passes_the_presets_own_validation() -> None:
    """Every preset passes the presets own validation."""
    for entry in await FileEntryCatalogue().list_entries():
        for preset in entry.presets:
            item = {
                "kind": preset.kind,
                "label": preset.label,
                "description": preset.description,
                "definition": preset.definition,
            }
            check_pack_item(item)  # includes the 64 KiB limit (Countries)
            check_definition(preset.kind, preset.definition)
            assert len(json.dumps(preset.definition).encode()) < 64 * 1024


async def test_ids_are_unique_and_starter_slugs_are_normalised() -> None:
    """Ids are unique and starter slugs are normalised."""
    entries = await FileEntryCatalogue().list_entries()
    assert len({e.id for e in entries}) == len(entries)
    for entry in entries:
        slugs = [t.slug for t in entry.item_types]
        slugs += [t.slug for t in entry.relationship_types]
        assert len(set(slugs)) == len(slugs)
        assert all(slugify(s) == s for s in slugs)
