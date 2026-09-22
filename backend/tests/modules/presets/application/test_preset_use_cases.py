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
from app.modules.presets.application.get_preset import GetPreset, GetPresetQuery
from app.modules.presets.application.list_presets import ListPresets, ListPresetsQuery
from app.modules.presets.application.update_preset import (
    UpdatePreset,
    UpdatePresetCommand,
)
from app.modules.presets.domain.errors import (
    BuiltinPresetError,
    InvalidPresetDefinitionError,
    PresetNotFoundError,
)
from app.modules.presets.domain.preset import Preset
from app.modules.presets.ports.unit_of_work import PresetRepos
from app.shared_kernel.actor import SYSTEM_ACTOR
from app.shared_kernel.unit_of_work import InMemoryUnitOfWork


def _empty_repos() -> PresetRepos:
    return PresetRepos(presets=InMemoryPresetRepository())


async def test_create_preset_persists_and_commits() -> None:
    """CreatePreset adds the preset to the repository and commits the unit of work."""
    repos = _empty_repos()
    uow = InMemoryUnitOfWork(repos)
    use_case = CreatePreset(uow)

    preset = await use_case.handle(
        CreatePresetCommand(
            kind="field", label="Condition", definition={"property": {"type": "string"}}
        ),
        SYSTEM_ACTOR,
    )

    assert await repos.presets.get(preset.id) is preset
    assert uow.committed is True


async def test_create_preset_rejects_a_malformed_definition() -> None:
    """A malformed definition is rejected and nothing is stored."""
    repos = _empty_repos()
    use_case = CreatePreset(InMemoryUnitOfWork(repos))

    with pytest.raises(InvalidPresetDefinitionError):
        await use_case.handle(
            CreatePresetCommand(kind="field", label="Condition", definition={}),
            SYSTEM_ACTOR,
        )

    assert await repos.presets.list(after=None, limit=10) == []


async def test_get_preset_returns_it() -> None:
    """GetPreset returns the stored preset."""
    repos = _empty_repos()
    preset = Preset.create(kind="field", label="Condition", definition={})
    await repos.presets.add(preset)

    result = await GetPreset(repos).handle(
        GetPresetQuery(preset_id=preset.id), SYSTEM_ACTOR
    )

    assert result is preset


async def test_get_preset_raises_for_a_missing_id() -> None:
    """An unknown id is a not-found error."""
    with pytest.raises(PresetNotFoundError):
        await GetPreset(_empty_repos()).handle(
            GetPresetQuery(preset_id=uuid.uuid4()), SYSTEM_ACTOR
        )


async def test_list_presets_filters_by_kind_and_q() -> None:
    """ListPresets can filter by kind and by a label search."""
    repos = _empty_repos()
    field = Preset.create(kind="field", label="Condition", definition={})
    other_kind = Preset.create(
        kind="choice_list", label="Condition list", definition={}
    )
    other_label = Preset.create(kind="field", label="Format", definition={})
    for preset in [field, other_kind, other_label]:
        await repos.presets.add(preset)

    by_kind = await ListPresets(repos).handle(
        ListPresetsQuery(kind="field"), SYSTEM_ACTOR
    )
    assert {p.id for p in by_kind} == {field.id, other_label.id}

    by_q = await ListPresets(repos).handle(
        ListPresetsQuery(q="condition"), SYSTEM_ACTOR
    )
    assert {p.id for p in by_q} == {field.id, other_kind.id}


async def test_update_preset_bumps_version_only_when_definition_changes() -> None:
    """A label/description edit keeps version 1; changing the definition bumps it."""
    repos = _empty_repos()
    preset = Preset.create(
        kind="field", label="Condition", definition={"property": {"type": "string"}}
    )
    await repos.presets.add(preset)
    uow = InMemoryUnitOfWork(repos)

    renamed = await UpdatePreset(uow).handle(
        UpdatePresetCommand(preset_id=preset.id, label="Grade"), SYSTEM_ACTOR
    )
    assert renamed.version == 1

    redefined = await UpdatePreset(uow).handle(
        UpdatePresetCommand(
            preset_id=preset.id,
            definition={"property": {"type": "number"}},
        ),
        SYSTEM_ACTOR,
    )
    assert redefined.version == 2
    assert uow.committed is True


async def test_update_preset_rejects_a_malformed_definition() -> None:
    """A malformed definition is rejected before saving."""
    repos = _empty_repos()
    preset = Preset.create(
        kind="choice_list", label="Grades", definition={"options": ["A"]}
    )
    await repos.presets.add(preset)

    with pytest.raises(InvalidPresetDefinitionError):
        await UpdatePreset(InMemoryUnitOfWork(repos)).handle(
            UpdatePresetCommand(preset_id=preset.id, definition={"options": []}),
            SYSTEM_ACTOR,
        )


async def test_update_preset_raises_for_a_missing_id() -> None:
    """An unknown id is a not-found error."""
    with pytest.raises(PresetNotFoundError):
        await UpdatePreset(InMemoryUnitOfWork(_empty_repos())).handle(
            UpdatePresetCommand(preset_id=uuid.uuid4(), label="X"), SYSTEM_ACTOR
        )


async def test_update_preset_raises_for_a_builtin_preset() -> None:
    """A built-in preset cannot be edited."""
    repos = _empty_repos()
    preset = Preset.create(kind="field", label="Condition", definition={}, builtin=True)
    await repos.presets.add(preset)

    with pytest.raises(BuiltinPresetError):
        await UpdatePreset(InMemoryUnitOfWork(repos)).handle(
            UpdatePresetCommand(preset_id=preset.id, label="Renamed"), SYSTEM_ACTOR
        )


async def test_delete_preset_soft_deletes_and_commits() -> None:
    """DeletePreset marks the preset deleted and commits."""
    repos = _empty_repos()
    preset = Preset.create(kind="field", label="Condition", definition={})
    await repos.presets.add(preset)
    uow = InMemoryUnitOfWork(repos)

    await DeletePreset(uow).handle(
        DeletePresetCommand(preset_id=preset.id), SYSTEM_ACTOR
    )

    assert await repos.presets.get(preset.id) is None
    assert uow.committed is True


async def test_delete_preset_raises_for_a_missing_id() -> None:
    """An unknown id is a not-found error."""
    with pytest.raises(PresetNotFoundError):
        await DeletePreset(InMemoryUnitOfWork(_empty_repos())).handle(
            DeletePresetCommand(preset_id=uuid.uuid4()), SYSTEM_ACTOR
        )


async def test_delete_preset_raises_for_a_builtin_preset() -> None:
    """A built-in preset cannot be deleted."""
    repos = _empty_repos()
    preset = Preset.create(kind="field", label="Condition", definition={}, builtin=True)
    await repos.presets.add(preset)

    with pytest.raises(BuiltinPresetError):
        await DeletePreset(InMemoryUnitOfWork(repos)).handle(
            DeletePresetCommand(preset_id=preset.id), SYSTEM_ACTOR
        )

    assert await repos.presets.get(preset.id) is preset
