import pytest

from app.modules.presets.domain.errors import BuiltinPresetError
from app.modules.presets.domain.preset import Preset
from app.shared_kernel.errors import ValidationError


def test_create_sets_fields_and_starts_at_version_one() -> None:
    """Preset.create sets fields, equal timestamps and version 1."""
    preset = Preset.create(
        kind="field",
        label="Condition",
        description="A condition grade.",
        definition={"property": {"type": "string"}},
    )

    assert preset.kind == "field"
    assert preset.label == "Condition"
    assert preset.description == "A condition grade."
    assert preset.definition == {"property": {"type": "string"}}
    assert preset.version == 1
    assert preset.builtin is False
    assert preset.created_at == preset.updated_at
    assert preset.is_deleted is False


@pytest.mark.parametrize("kind", ["field", "field_set", "choice_list"])
def test_create_accepts_every_valid_kind(kind: str) -> None:
    """Every documented kind is accepted."""
    Preset.create(kind=kind, label="X", definition={})


def test_create_rejects_an_unknown_kind() -> None:
    """A kind outside the valid set is rejected."""
    with pytest.raises(ValidationError):
        Preset.create(kind="not-a-kind", label="X", definition={})


def test_create_rejects_a_blank_label() -> None:
    """A blank label is rejected."""
    with pytest.raises(ValidationError):
        Preset.create(kind="field", label="   ", definition={})


def test_update_changes_label_and_description_without_bumping_version() -> None:
    """A label/description-only edit leaves the definition and version untouched."""
    preset = Preset.create(kind="field", label="Condition", definition={"a": 1})

    preset.update(label="Grade", description="Renamed")

    assert preset.label == "Grade"
    assert preset.description == "Renamed"
    assert preset.definition == {"a": 1}
    assert preset.version == 1


def test_update_with_a_definition_bumps_version() -> None:
    """Changing the definition increments version."""
    preset = Preset.create(kind="field", label="Condition", definition={"a": 1})

    preset.update(definition={"a": 2})

    assert preset.definition == {"a": 2}
    assert preset.version == 2


def test_update_rejects_a_blank_label() -> None:
    """A blank label is rejected on update too."""
    preset = Preset.create(kind="field", label="Condition", definition={})

    with pytest.raises(ValidationError):
        preset.update(label="  ")


def test_update_raises_for_a_builtin_preset() -> None:
    """A built-in preset cannot be edited."""
    preset = Preset.create(kind="field", label="Condition", definition={}, builtin=True)

    with pytest.raises(BuiltinPresetError):
        preset.update(label="Renamed")


def test_soft_delete_raises_for_a_builtin_preset() -> None:
    """A built-in preset cannot be deleted."""
    preset = Preset.create(kind="field", label="Condition", definition={}, builtin=True)

    with pytest.raises(BuiltinPresetError):
        preset.soft_delete()

    assert preset.is_deleted is False


def test_soft_delete_marks_a_non_builtin_preset_deleted() -> None:
    """An ordinary preset can be soft-deleted."""
    preset = Preset.create(kind="field", label="Condition", definition={})

    preset.soft_delete()

    assert preset.is_deleted is True
