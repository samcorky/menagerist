import uuid
from typing import TYPE_CHECKING

import pytest

from app.modules.presets.adapters.persistence.preset_repository import (
    SqlAlchemyPresetRepository,
)
from app.modules.presets.domain.preset import Preset

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


def _fields(preset: Preset) -> tuple[object, ...]:
    return (
        preset.id,
        preset.kind,
        preset.label,
        preset.description,
        preset.definition,
        preset.version,
        preset.builtin,
        preset.created_at,
        preset.updated_at,
        preset.deleted_at,
    )


async def test_add_and_get_round_trips(db_session: AsyncSession) -> None:
    """A preset added to the repository can be retrieved by id, fields intact."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(
        kind="field",
        label="Condition",
        description="A condition grade.",
        definition={"property": {"type": "string", "enum": ["Mint", "VG+"]}},
    )

    await repository.add(preset)
    result = await repository.get(preset.id)

    assert result is not None
    assert _fields(result) == _fields(preset)


async def test_get_returns_none_for_missing_preset(db_session: AsyncSession) -> None:
    """get() returns None for an id that was never added."""
    repository = SqlAlchemyPresetRepository(db_session)

    assert await repository.get(uuid.uuid4()) is None


async def test_get_returns_none_for_a_soft_deleted_preset(
    db_session: AsyncSession,
) -> None:
    """get() treats a soft-deleted preset as if it doesn't exist."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(kind="field", label="Condition", definition={})
    await repository.add(preset)

    preset.soft_delete()
    await repository.save(preset)

    assert await repository.get(preset.id) is None


async def test_save_persists_a_version_bump(db_session: AsyncSession) -> None:
    """A definition change and its version bump survive a save/get round trip."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(kind="field", label="Condition", definition={"a": 1})
    await repository.add(preset)

    preset.update(definition={"a": 2})
    await repository.save(preset)
    result = await repository.get(preset.id)

    assert result is not None
    assert result.definition == {"a": 2}
    assert result.version == 2


async def test_list_orders_by_id_ascending(db_session: AsyncSession) -> None:
    """list() returns presets ordered by id ascending, regardless of insert order."""
    repository = SqlAlchemyPresetRepository(db_session)
    presets = [
        Preset.create(kind="field", label=f"P{i}", definition={}) for i in range(3)
    ]
    for preset in reversed(presets):
        await repository.add(preset)

    result = await repository.list(after=None, limit=10)

    assert [p.id for p in result] == sorted(p.id for p in presets)


async def test_list_respects_after_and_limit(db_session: AsyncSession) -> None:
    """list() pages using `after` and `limit`."""
    repository = SqlAlchemyPresetRepository(db_session)
    presets = [
        Preset.create(kind="field", label=f"P{i}", definition={}) for i in range(3)
    ]
    for preset in presets:
        await repository.add(preset)
    ordered = sorted(presets, key=lambda p: p.id)

    page = await repository.list(after=None, limit=2)
    assert [p.id for p in page] == [p.id for p in ordered[:2]]

    rest = await repository.list(after=page[-1].id, limit=10)
    assert [p.id for p in rest] == [p.id for p in ordered[2:]]


async def test_list_filters_by_kind_and_label_search(db_session: AsyncSession) -> None:
    """list() can filter by `kind` and by a case-insensitive `q` on the label."""
    repository = SqlAlchemyPresetRepository(db_session)
    field = Preset.create(kind="field", label="Condition Grade", definition={})
    choice_list = Preset.create(
        kind="choice_list", label="Condition List", definition={}
    )
    other = Preset.create(kind="field", label="Format", definition={})
    for preset in [field, choice_list, other]:
        await repository.add(preset)

    by_kind = await repository.list(after=None, limit=10, kind="choice_list")
    assert [p.id for p in by_kind] == [choice_list.id]

    by_q = await repository.list(after=None, limit=10, q="condition")
    assert {p.id for p in by_q} == {field.id, choice_list.id}


async def test_list_excludes_soft_deleted_presets(db_session: AsyncSession) -> None:
    """A soft-deleted preset never appears in list()."""
    repository = SqlAlchemyPresetRepository(db_session)
    preset = Preset.create(kind="field", label="Condition", definition={})
    await repository.add(preset)
    preset.soft_delete()
    await repository.save(preset)

    assert await repository.list(after=None, limit=10) == []
