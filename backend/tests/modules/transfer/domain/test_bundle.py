import pytest

from app.modules.transfer.domain.bundle import unportable_condition


@pytest.mark.parametrize(
    "definition",
    [
        {"v": 1, "where": {"kind": "type", "in": ["record"]}},
        {"v": 1, "where": {"kind": "connection", "type": "wrote"}},
        {"v": 1, "where": {"op": "and", "children": []}},
        "text",
        5,
    ],
)
def test_a_rule_made_of_portable_conditions_may_travel(definition: object) -> None:
    """Nothing in these names an id a bundle cannot know."""
    assert unportable_condition(definition) is None


def test_a_condition_on_another_collection_cannot_travel() -> None:
    """The path leads to the condition and the reason says why."""
    definition = {
        "where": {
            "op": "and",
            "children": [
                {"kind": "type", "in": ["record"]},
                {"kind": "collection", "id": "x"},
            ],
        }
    }

    assert unportable_condition(definition) == (
        "where.children[1]",
        "a collection condition cannot be in a bundle",
    )


def test_a_connection_to_one_item_cannot_travel() -> None:
    """A connection that names an item names an id the bundle cannot know."""
    definition = {"where": {"kind": "connection", "type": "wrote", "item": "abc"}}

    assert unportable_condition(definition) == (
        "where",
        "a connection to one item cannot be in a bundle",
    )
