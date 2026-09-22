import uuid

from app.modules.presets.adapters.persistence.in_memory_preset_repository import (
    InMemoryPresetRepository,
)
from app.modules.presets.domain.preset import Preset


async def test_add_and_get_round_trips() -> None:
    """A preset added to the repository can be retrieved by id."""
    repository = InMemoryPresetRepository()
    preset = Preset.create(kind="field", label="Condition", definition={})

    await repository.add(preset)

    assert await repository.get(preset.id) is preset


async def test_get_returns_none_for_missing_or_deleted() -> None:
    """get() returns None for an unknown id and for a soft-deleted preset."""
    repository = InMemoryPresetRepository()
    preset = Preset.create(kind="field", label="Condition", definition={})
    await repository.add(preset)

    assert await repository.get(uuid.uuid4()) is None

    preset.soft_delete()
    await repository.save(preset)
    assert await repository.get(preset.id) is None


async def test_list_orders_by_id_and_respects_after_and_limit() -> None:
    """list() returns non-deleted presets ordered by id, paginated."""
    repository = InMemoryPresetRepository()
    presets = [
        Preset.create(kind="field", label=f"P{i}", definition={}) for i in range(3)
    ]
    gone = Preset.create(kind="field", label="Gone", definition={})
    gone.soft_delete()
    for p in [*presets, gone]:
        await repository.add(p)

    page = await repository.list(after=None, limit=2)
    assert [p.id for p in page] == sorted(p.id for p in presets)[:2]
    rest = await repository.list(after=page[-1].id, limit=10)
    assert [p.id for p in rest] == sorted(p.id for p in presets)[2:]


async def test_list_filters_by_kind() -> None:
    """list() can be scoped to one kind."""
    repository = InMemoryPresetRepository()
    field = Preset.create(kind="field", label="Condition", definition={})
    choice_list = Preset.create(kind="choice_list", label="Grades", definition={})
    await repository.add(field)
    await repository.add(choice_list)

    result = await repository.list(after=None, limit=10, kind="choice_list")

    assert [p.id for p in result] == [choice_list.id]


async def test_list_filters_by_label_search_case_insensitively() -> None:
    """list() matches `q` against the label, ignoring case."""
    repository = InMemoryPresetRepository()
    match = Preset.create(kind="field", label="Condition Grade", definition={})
    other = Preset.create(kind="field", label="Format", definition={})
    await repository.add(match)
    await repository.add(other)

    result = await repository.list(after=None, limit=10, q="condition")

    assert [p.id for p in result] == [match.id]
