from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from app.modules.presets.adapters.persistence.models import PresetModel
from app.modules.presets.adapters.persistence.preset_repository import (
    SqlAlchemyPresetRepository,
)
from app.modules.presets.application.preset_definitions import check_definition
from app.modules.presets.domain.errors import BuiltinPresetError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


async def test_migration_seeds_the_builtin_choice_lists(
    db_session: AsyncSession,
) -> None:
    """The migration leaves the two built-in choice lists in the table, read-only."""
    result = await db_session.execute(
        select(PresetModel).where(PresetModel.builtin.is_(True))
    )
    builtins = {model.label: model for model in result.scalars()}

    assert {"Condition grades", "Countries"} <= set(builtins)
    assert builtins["Countries"].kind == "choice_list"
    assert "United Kingdom" in builtins["Countries"].definition["options"]
    assert "Mint" in builtins["Condition grades"].definition["options"]


async def test_builtin_lists_cannot_be_deleted(db_session: AsyncSession) -> None:
    """A seeded built-in refuses soft delete through the domain."""
    repository = SqlAlchemyPresetRepository(db_session)
    model = (
        await db_session.execute(
            select(PresetModel).where(PresetModel.label == "Countries")
        )
    ).scalar_one()
    preset = await repository.get(model.id)
    assert preset is not None

    with pytest.raises(BuiltinPresetError):
        preset.soft_delete()


async def test_seeded_field_presets_are_valid_and_read_only(
    db_session: AsyncSession,
) -> None:
    """Seeded fields and field groups pass the shape check and cannot be deleted."""
    result = await db_session.execute(
        select(PresetModel).where(
            PresetModel.builtin.is_(True), PresetModel.kind.in_(["field", "field_set"])
        )
    )
    models = list(result.scalars())
    labels = {m.label for m in models}
    assert {
        "Condition",
        "Rating",
        "Purchase details",
        "Vinyl details",
        "Review",
        "Recipe",
    } <= labels

    repository = SqlAlchemyPresetRepository(db_session)
    for model in models:
        check_definition(model.kind, model.definition)
        preset = await repository.get(model.id)
        assert preset is not None
        with pytest.raises(BuiltinPresetError):
            preset.soft_delete()
