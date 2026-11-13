"""Presets belong to one person: no one reads or changes another's."""

import uuid

import pytest

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.application.create_preset import (
    CreatePreset,
    CreatePresetCommand,
)
from app.modules.presets.application.delete_preset import (
    DeletePreset,
    DeletePresetCommand,
)
from app.modules.presets.application.export_presets import (
    ExportPresets,
    ExportPresetsQuery,
)
from app.modules.presets.application.get_preset import GetPreset, GetPresetQuery
from app.modules.presets.application.import_presets import (
    ImportPresets,
    ImportPresetsCommand,
)
from app.modules.presets.application.list_presets import ListPresets, ListPresetsQuery
from app.modules.presets.application.update_preset import (
    UpdatePreset,
    UpdatePresetCommand,
)
from app.modules.presets.domain.errors import PresetNotFoundError
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.access_guard import InMemoryAccessGuard
from app.shared_kernel.actor import Actor
from app.shared_kernel.content_filter import ContentFilter
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork

ALICE = Actor(id=uuid.UUID(int=101), roles=frozenset({"member"}))
BOB = Actor(id=uuid.UUID(int=102), roles=frozenset({"member"}))
GUARD = InMemoryAccessGuard()
_ITEM = {
    "kind": "choice_list",
    "label": "Grades",
    "description": None,
    "definition": {"options": ["Mint"]},
}


async def _alices(repos: PresetRepos) -> Preset:
    preset = Preset.create(
        owner_id=ALICE.id,
        kind="choice_list",
        label="Grades",
        definition={"options": ["A"]},
    )
    await repos.presets.add(preset)
    return preset


async def test_create_stamps_the_actor_as_owner() -> None:
    """A created preset belongs to whoever made it."""
    repos = PresetRepos(presets=InMemoryPresetRepository())

    preset = await CreatePreset(InMemoryUnitOfWork(repos), GUARD).handle(
        CreatePresetCommand(
            kind="field", label="X", definition={"property": {"type": "string"}}
        ),
        ALICE,
    )

    assert preset.owner_id == ALICE.id


async def test_get_hides_another_persons_preset() -> None:
    """A guessed id of someone else's preset is not found."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    preset = await _alices(repos)

    assert (
        await GetPreset(repos, GUARD).handle(GetPresetQuery(preset_id=preset.id), ALICE)
        is preset
    )
    with pytest.raises(PresetNotFoundError):
        await GetPreset(repos, GUARD).handle(GetPresetQuery(preset_id=preset.id), BOB)


async def test_list_shows_only_the_actors_presets() -> None:
    """Listing never includes another person's presets."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    await _alices(repos)

    assert await ListPresets(repos, GUARD).handle(ListPresetsQuery(), BOB) == []
    assert len(await ListPresets(repos, GUARD).handle(ListPresetsQuery(), ALICE)) == 1


async def test_update_and_delete_cannot_reach_another_persons_preset() -> None:
    """Editing or deleting someone else's preset is not found, and changes nothing."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    preset = await _alices(repos)
    uow = InMemoryUnitOfWork(repos)

    with pytest.raises(PresetNotFoundError):
        await UpdatePreset(uow, GUARD).handle(
            UpdatePresetCommand(preset_id=preset.id, label="Hijacked"), BOB
        )
    with pytest.raises(PresetNotFoundError):
        await DeletePreset(uow, GUARD).handle(
            DeletePresetCommand(preset_id=preset.id), BOB
        )

    assert preset.label == "Grades"
    assert preset.deleted_at is None


async def test_export_cannot_reach_another_persons_preset() -> None:
    """Exporting someone else's preset id is not found."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    preset = await _alices(repos)

    with pytest.raises(PresetNotFoundError):
        await ExportPresets(repos, GUARD).handle(
            ExportPresetsQuery(ids=[preset.id]), BOB
        )


async def test_import_deduplicates_per_owner() -> None:
    """Importing a pack another person already has still creates your own copy."""
    repos = PresetRepos(presets=InMemoryPresetRepository())
    command = ImportPresetsCommand(
        pack_format="menagerist-presets", pack_version=1, items=[dict(_ITEM)]
    )

    first = await ImportPresets(InMemoryUnitOfWork(repos), GUARD).handle(command, ALICE)
    second = await ImportPresets(InMemoryUnitOfWork(repos), GUARD).handle(command, BOB)
    again = await ImportPresets(InMemoryUnitOfWork(repos), GUARD).handle(command, BOB)

    assert (first.created, second.created, again.created) == (1, 1, 0)
    assert first.items[0].id != second.items[0].id
    bobs = await repos.presets.list(
        scope=ContentFilter.of(BOB.id), after=None, limit=10
    )
    assert [p.id for p in bobs] == [second.items[0].id]
