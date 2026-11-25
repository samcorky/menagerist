import pytest

from app.modules.transfer.domain.bundle import (
    MAX_COLLECTION_NAME,
    MAX_COLLECTIONS,
    MAX_CONNECTIONS,
    MAX_ITEMS,
    Bundle,
    BundleCollection,
    BundleConnection,
    BundleItem,
    BundleItemType,
    BundleRelationshipType,
    unportable_condition,
)
from app.modules.transfer.domain.errors import InvalidBundleError


def _items(count: int) -> tuple[BundleItem, ...]:
    return tuple(BundleItem(ref=f"i{n}", type_ref="t", name="x") for n in range(count))


def test_a_bundle_at_its_limits_is_accepted() -> None:
    """The limits are inclusive."""
    items = _items(MAX_ITEMS)
    connection = BundleConnection(source_ref="i0", target_ref="i1", type_ref="r")
    collections = tuple(
        BundleCollection(ref=f"c{n}", name="x", item_refs=("i0",))
        for n in range(MAX_COLLECTIONS)
    )

    bundle = Bundle(
        id="b",
        items=items,
        connections=(connection,) * MAX_CONNECTIONS,
        collections=collections,
    )

    assert len(bundle.items) == MAX_ITEMS


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"items": _items(MAX_ITEMS + 1)}, "at most 500 items"),
        (
            {
                "connections": (
                    BundleConnection(source_ref="a", target_ref="b", type_ref="r"),
                )
                * (MAX_CONNECTIONS + 1)
            },
            "at most 2000 connections",
        ),
        (
            {
                "collections": tuple(
                    BundleCollection(ref=f"c{n}", name="x")
                    for n in range(MAX_COLLECTIONS + 1)
                )
            },
            "at most 100 collections",
        ),
    ],
)
def test_a_bundle_over_a_limit_is_refused(
    kwargs: dict[str, tuple[object, ...]], message: str
) -> None:
    """A bundle cannot hold more than the limits, whatever its source."""
    with pytest.raises(InvalidBundleError, match=message):
        Bundle(id="b", **kwargs)  # type: ignore[arg-type]


@pytest.mark.parametrize("name", ["", "   ", "x" * (MAX_COLLECTION_NAME + 1)])
def test_a_collection_needs_a_name_of_a_usable_length(name: str) -> None:
    """The name limits are the collections module's."""
    with pytest.raises(InvalidBundleError, match="needs a name of 1 to 120"):
        Bundle(id="b", collections=(BundleCollection(ref="c", name=name),))


def test_a_collection_may_not_list_an_item_twice() -> None:
    """A repeated item ref is a mistake in the file."""
    collection = BundleCollection(ref="c", name="x", item_refs=("a", "a"))

    with pytest.raises(InvalidBundleError, match="lists an item twice"):
        Bundle(id="b", collections=(collection,))


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


def test_a_relationship_holder_is_one_of_three() -> None:
    """`source`, `target` or `none`; the default holds nothing."""
    assert BundleRelationshipType(ref="r", slug="r", label="R").holder == "none"
    with pytest.raises(InvalidBundleError, match="unknown holder"):
        BundleRelationshipType(ref="r", slug="r", label="R", holder="middle")


def _types(**parents: str | None) -> tuple[BundleItemType, ...]:
    """Item types named by ref, each with the parent ref given for it."""
    return tuple(
        BundleItemType(ref=ref, slug=ref, label=ref.title(), parent=parent)
        for ref, parent in parents.items()
    )


def test_an_item_type_may_name_a_parent_in_the_same_bundle() -> None:
    """A subtype and its parent, in either order, make a bundle."""
    parent_first = Bundle(id="b", item_types=_types(memo=None, poster="memo"))
    subtype_first = Bundle(id="b", item_types=_types(poster="memo", memo=None))

    assert [t.parent for t in parent_first.item_types] == [None, "memo"]
    assert [t.parent for t in subtype_first.item_types] == ["memo", None]


def test_a_parent_must_be_a_type_in_the_bundle() -> None:
    """A subtype whose parent is not in the file could not be imported on its own."""
    with pytest.raises(InvalidBundleError, match=r"'poster'.*parent 'memo'.*not in"):
        Bundle(id="b", item_types=_types(poster="memo"))


def test_a_type_cannot_be_its_own_parent() -> None:
    """Naming itself is refused."""
    with pytest.raises(InvalidBundleError, match="its own parent"):
        Bundle(id="b", item_types=_types(poster="poster"))


def test_a_parent_cannot_have_a_parent() -> None:
    """Only one level of parent types is supported."""
    with pytest.raises(InvalidBundleError, match="one level"):
        Bundle(id="b", item_types=_types(top=None, memo="top", poster="memo"))


def test_a_subtype_cannot_reuse_its_parents_field_keys() -> None:
    """The same key in both would make two answers for one field."""
    parent = BundleItemType(
        ref="memo",
        slug="memo",
        label="Memo",
        attributes_schema={"properties": {"condition": {}, "value": {}}},
    )
    subtype = BundleItemType(
        ref="poster",
        slug="poster",
        label="Poster",
        parent="memo",
        attributes_schema={"properties": {"width": {}, "condition": {}}},
    )

    with pytest.raises(InvalidBundleError, match="condition"):
        Bundle(id="b", item_types=(parent, subtype))
