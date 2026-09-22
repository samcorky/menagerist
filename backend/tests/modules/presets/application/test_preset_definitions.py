import pytest

from app.modules.presets.application.preset_definitions import check_definition
from app.modules.presets.domain.errors import InvalidPresetDefinitionError


def test_check_definition_accepts_a_well_shaped_field() -> None:
    """A property with a type is a valid field definition."""
    check_definition("field", {"property": {"type": "string"}})


@pytest.mark.parametrize(
    "definition",
    [{}, {"property": {}}, {"property": {"title": "X"}}, {"property": "nope"}],
)
def test_check_definition_rejects_a_malformed_field(
    definition: dict[str, object],
) -> None:
    """Each malformed shape is rejected."""
    with pytest.raises(InvalidPresetDefinitionError):
        check_definition("field", definition)


def test_check_definition_accepts_a_well_shaped_field_set() -> None:
    """A section label plus typed properties passes."""
    check_definition(
        "field_set",
        {"section": "Purchase details", "properties": [{"type": "number"}]},
    )


@pytest.mark.parametrize(
    "definition",
    [
        {},
        {"section": "", "properties": [{"type": "number"}]},
        {"section": "X", "properties": []},
        {"section": "X", "properties": [{"no_type": True}]},
        {"section": "X", "properties": "nope"},
    ],
)
def test_check_definition_rejects_a_malformed_field_set(
    definition: dict[str, object],
) -> None:
    """Each malformed shape is rejected."""
    with pytest.raises(InvalidPresetDefinitionError):
        check_definition("field_set", definition)


def test_check_definition_accepts_a_well_shaped_choice_list() -> None:
    """A non-empty list of strings passes."""
    check_definition("choice_list", {"options": ["Mint", "Near Mint"]})


@pytest.mark.parametrize(
    "definition",
    [{}, {"options": []}, {"options": ["", "Mint"]}, {"options": [1, 2]}],
)
def test_check_definition_rejects_a_malformed_choice_list(
    definition: dict[str, object],
) -> None:
    """Each malformed shape is rejected."""
    with pytest.raises(InvalidPresetDefinitionError):
        check_definition("choice_list", definition)


def test_check_definition_rejects_an_unknown_kind() -> None:
    """An unrecognised kind is rejected regardless of the definition."""
    with pytest.raises(InvalidPresetDefinitionError):
        check_definition("not-a-kind", {})
