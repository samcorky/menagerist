from dataclasses import replace

import pytest

from app.modules.graph.domain.aggregate import (
    GroupBy,
    GroupValue,
    MeasureValue,
    arrange_groups,
    parse_group_by,
)
from app.modules.graph.domain.query import InvalidQueryError


def test_parses_a_field_grouping_with_every_option() -> None:
    """A grouping carries the field and how to order and cut the groups."""
    parsed = parse_group_by(
        {
            "by": "field",
            "type": "film",
            "key": "format",
            "order": "measure",
            "measure": 1,
            "descending": False,
            "limit": 5,
        }
    )

    assert parsed == GroupBy(
        by="field",
        type="film",
        key="format",
        order="measure",
        measure=1,
        descending=False,
        limit=5,
    )


def test_a_type_or_tag_grouping_needs_nothing_else() -> None:
    """Type and tag groupings take defaults: by key, ascending, 100 groups."""
    parsed = parse_group_by({"by": "tag"})

    assert parsed == GroupBy(by="tag")
    assert parsed.is_descending is False
    assert GroupBy(by="tag", order="count").is_descending is True


@pytest.mark.parametrize(
    "raw",
    [
        "tag",
        {"by": "colour"},
        {"by": "tag", "colour": 1},
        {"by": "field"},
        {"by": "field", "type": "film"},
        {"by": "tag", "key": "format", "type": "film"},
        {"by": "tag", "order": "alphabet"},
        {"by": "tag", "order": "measure"},
        {"by": "tag", "order": "measure", "measure": -1},
        {"by": "tag", "order": "measure", "measure": True},
        {"by": "tag", "measure": 0},
        {"by": "tag", "descending": "yes"},
        {"by": "tag", "limit": 0},
        {"by": "tag", "limit": 101},
        {"by": "tag", "limit": True},
    ],
)
def test_refuses_a_malformed_grouping(raw: object) -> None:
    """Anything that is not a grouping is refused at `group_by`."""
    with pytest.raises(InvalidQueryError) as caught:
        parse_group_by(raw)

    assert caught.value.path == "group_by"


def _group(key: str | None, count: int, value: float | None = None) -> GroupValue:
    return GroupValue(key=key, count=count, values=(MeasureValue(value=value),))


GROUPS = [_group("b", 3, 9), _group(None, 5), _group("a", 3, 1), _group("c", 1, 9)]


def _keys(groups: list[GroupValue]) -> list[str | None]:
    return [g.key for g in groups]


def test_orders_by_key_with_the_unset_group_last() -> None:
    """Keys ascend, and the unset group comes after them whichever way they run."""
    ascending, _ = arrange_groups(GROUPS, GroupBy(by="tag"))
    descending, _ = arrange_groups(GROUPS, GroupBy(by="tag", descending=True))

    assert _keys(ascending) == ["a", "b", "c", None]
    assert _keys(descending) == ["c", "b", "a", None]


def test_orders_by_count_high_to_low_with_ties_by_key() -> None:
    """The biggest group is first, and equal sizes keep key order."""
    ordered, _ = arrange_groups(GROUPS, GroupBy(by="tag", order="count"))

    assert _keys(ordered) == [None, "a", "b", "c"]


def test_orders_by_a_measure_with_empty_values_last() -> None:
    """A group with no value for the measure sorts after the ones that have one."""
    by = GroupBy(by="tag", order="measure", measure=0)

    high, _ = arrange_groups(GROUPS, by)
    low, _ = arrange_groups(GROUPS, replace(by, descending=False))

    assert _keys(high) == ["b", "c", "a", None]
    assert _keys(low) == ["a", "b", "c", None]


def test_splits_the_groups_the_limit_leaves_out() -> None:
    """The groups past the limit are returned apart, in order."""
    shown, hidden = arrange_groups(GROUPS, GroupBy(by="tag", limit=3))

    assert _keys(shown) == ["a", "b", "c"]
    assert _keys(hidden) == [None]
