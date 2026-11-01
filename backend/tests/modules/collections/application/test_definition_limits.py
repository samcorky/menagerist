from typing import Any

import pytest

from app.modules.collections.application.definition_limits import (
    MAX_DEFINITION_BYTES,
    MAX_DEFINITION_DEPTH,
    ensure_definition_within_limits,
)
from app.modules.collections.domain.errors import InvalidDefinitionError


def _nested(levels: int) -> dict[str, Any]:
    """A definition whose deepest object sits `levels` levels down."""
    node: dict[str, Any] = {}
    for _ in range(levels - 1):
        node = {"d": node}
    return node


def test_a_maximal_valid_query_is_within_the_limits() -> None:
    """Four nested groups holding a money operand reach exactly the depth limit."""
    condition = {
        "kind": "field",
        "type": "t",
        "key": "k",
        "op": "in",
        "value": [{"value": 1.5, "currency": "GBP"}],
    }
    group: dict[str, Any] = {"op": "and", "children": [condition]}
    for _ in range(3):
        group = {"op": "and", "children": [group]}
    ensure_definition_within_limits({"v": 1, "where": group, "sort": []})


def test_depth_at_the_limit_passes_and_one_more_fails() -> None:
    """The depth limit is inclusive."""
    ensure_definition_within_limits(_nested(MAX_DEFINITION_DEPTH))
    with pytest.raises(InvalidDefinitionError, match="nest up to"):
        ensure_definition_within_limits(_nested(MAX_DEFINITION_DEPTH + 1))


def test_lists_count_towards_depth() -> None:
    """Lists nest like objects."""
    deep: object = 1
    for _ in range(MAX_DEFINITION_DEPTH):
        deep = [deep]
    with pytest.raises(InvalidDefinitionError, match="nest up to"):
        ensure_definition_within_limits({"v": deep})


def test_very_deep_nesting_is_refused_without_recursing() -> None:
    """800 levels are rejected cleanly, not with a RecursionError."""
    with pytest.raises(InvalidDefinitionError, match="nest up to"):
        ensure_definition_within_limits(_nested(800))


@pytest.mark.parametrize(
    "definition",
    [
        {"v": 1, "note": "a\x00b"},
        {"v": 1, "a\x00b": 1},
        {"v": 1, "list": ["fine", "a\x00"]},
    ],
)
def test_nul_is_refused_in_keys_and_values(definition: dict[str, Any]) -> None:
    """Postgres cannot store NUL in text, so it never gets that far."""
    with pytest.raises(InvalidDefinitionError, match="NUL"):
        ensure_definition_within_limits(definition)


@pytest.mark.parametrize(
    "definition", [{"v": 1, "note": "\ud800"}, {"v": 1, "\udfff": 1}]
)
def test_a_lone_surrogate_is_refused(definition: dict[str, Any]) -> None:
    """Text that is not valid UTF-8 cannot be stored or returned."""
    with pytest.raises(InvalidDefinitionError, match="Unicode"):
        ensure_definition_within_limits(definition)


@pytest.mark.parametrize("number", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_number_is_refused(number: float) -> None:
    """JSONB has no NaN or infinity."""
    with pytest.raises(InvalidDefinitionError, match="NaN"):
        ensure_definition_within_limits({"v": 1, "n": number})


def test_size_is_measured_in_utf8_bytes() -> None:
    """The limit is on the encoded size, so wide characters count in full."""
    fits = {"v": "x" * (MAX_DEFINITION_BYTES - len('{"v": ""}'))}
    ensure_definition_within_limits(fits)
    with pytest.raises(InvalidDefinitionError, match="KiB"):
        ensure_definition_within_limits({"v": "x" * MAX_DEFINITION_BYTES})
    with pytest.raises(InvalidDefinitionError, match="KiB"):
        ensure_definition_within_limits({"v": "é" * (MAX_DEFINITION_BYTES // 2)})
