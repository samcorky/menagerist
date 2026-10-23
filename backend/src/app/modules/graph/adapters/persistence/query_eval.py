"""Evaluate a query tree against a node in Python.

The reference semantics: `query_sql.py` must agree with this module on every
scenario in `test_node_search.py`.
"""

import sys
from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date
from typing import TYPE_CHECKING, Any

from app.modules.graph.adapters.persistence.text_match import (
    description_blank,
    fold,
    sort_key,
    text_matches,
)
from app.modules.graph.domain.query import (
    COMPLEMENT_OPERATORS,
    CollectionCondition,
    Condition,
    Cursor,
    DateCondition,
    DescriptionCondition,
    FavouriteCondition,
    FieldCondition,
    FieldReference,
    Group,
    ManualTarget,
    MediaCondition,
    Money,
    NameCondition,
    Operand,
    RelativeDate,
    ResolvedQuery,
    SearchHit,
    SmartTarget,
    SortKey,
    SortValue,
    StaleTarget,
    TagCondition,
    TextCondition,
    TypeCondition,
)

if TYPE_CHECKING:
    from app.modules.graph.adapters.persistence.query_env import QueryEnv
    from app.modules.graph.domain.node import Node

_NUMERIC = frozenset({"number", "duration", "rating"})
_TEXTUAL = frozenset({"text", "url", "email", "phone", "longtext"})
_MISSING = object()


def _number(value: object) -> float | None:
    """The value as a float, or None if it is not a number a float can hold."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    # Exact for ints; also rejects NaN and infinity. Matches `_num` in SQL.
    if not abs(value) <= sys.float_info.max:
        return None
    return float(value)


def _compare(op: str, left: Any, right: Any) -> bool:  # noqa: ANN401
    match op:
        case "=":
            return bool(left == right)
        case ">":
            return bool(left > right)
        case ">=":
            return bool(left >= right)
        case "<":
            return bool(left < right)
        case "<=":
            return bool(left <= right)
    raise AssertionError(op)


def _is_empty(value: object) -> bool:
    return value is None or value in ("", [])


def _reference(operand: FieldReference, node: Node, kind: str) -> Any:  # noqa: ANN401
    """Read the referenced attribute as `kind`, or `_MISSING` if unusable."""
    other = node.attributes.get(operand.key)
    if kind == "money":
        if not isinstance(other, Mapping):
            return _MISSING
        amount = _number(other.get("value"))
        if amount is None:
            return _MISSING
        return Money(value=amount, currency=str(other.get("currency")))
    if kind == "date":
        return other if isinstance(other, str) else _MISSING
    number = _number(other)
    return _MISSING if number is None else number


def _resolve(operand: Operand, node: Node, kind: str, today: date) -> Any:  # noqa: ANN401
    """Turn an operand into a plain comparable value, or `_MISSING`."""
    if isinstance(operand, tuple):
        parts = [_resolve(item, node, kind, today) for item in operand]
        return _MISSING if any(p is _MISSING for p in parts) else tuple(parts)
    if isinstance(operand, RelativeDate):
        return operand.resolve(today).isoformat()
    if isinstance(operand, FieldReference):
        return _reference(operand, node, kind)
    return operand


def _test_numeric(op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    number = _number(value)
    if number is None:
        return False
    if op == "between":
        return bool(operand[0] <= number <= operand[1])
    return _compare(op, number, operand)


def _test_money(op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    if not isinstance(value, Mapping):
        return False
    amount = _number(value.get("value"))
    if amount is None:
        return False
    if op == "between":
        low, high = operand
        return bool(
            value.get("currency") == low.currency == high.currency
            and low.value <= amount <= high.value
        )
    return value.get("currency") == operand.currency and _compare(
        op, amount, operand.value
    )


def _test_date(op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    if not isinstance(value, str):
        return False
    if op == "between":
        return bool(operand[0] <= value <= operand[1])
    return _compare(op, value, operand)


def _test_partial_date(op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    """Compare only as many characters as the operand gives (year, month, day)."""
    if not isinstance(value, str):
        return False
    if op == "between":
        low, high = operand
        return bool(value[: len(low)] >= low and value[: len(high)] <= high)
    return _compare(op, value[: len(operand)], operand)


def _test_text(kind: str, op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    """Text kinds fold case and accents; a choice is compared exactly."""
    if not isinstance(value, str):
        return False
    if kind == "choice":
        return value == operand if op == "=" else value in operand
    folded = fold(value)
    if op == "~":
        return bool(fold(operand) in folded)
    if op == "in":
        return folded in {fold(item) for item in operand}
    return bool(folded == fold(operand))


def _test_checklist(op: str, value: object) -> bool:
    if not isinstance(value, list):
        return False
    rows = [row for row in value if isinstance(row, Mapping)]
    open_rows = any(row.get("done") is not True for row in rows)
    return open_rows if op == "incomplete" else bool(rows) and not open_rows


def _test(kind: str, op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    """Whether a present, non-null `value` satisfies `op` against `operand`."""
    if kind in _NUMERIC:
        return _test_numeric(op, value, operand)
    if kind == "money":
        return _test_money(op, value, operand)
    if kind == "date":
        return _test_date(op, value, operand)
    if kind == "partialdate":
        return _test_partial_date(op, value, operand)
    if kind in _TEXTUAL or kind == "choice":
        return _test_text(kind, op, value, operand)
    if kind == "boolean":
        return value is operand
    if kind == "multichoice":
        return isinstance(value, list) and all(item in value for item in operand)
    return _test_checklist(op, value)


def _candidates(node: Node, condition: FieldCondition) -> list[object]:
    value = node.attributes.get(condition.key)
    if condition.sub_key is None:
        return [value]
    if not isinstance(value, list):
        return []
    return [row.get(condition.sub_key) for row in value if isinstance(row, Mapping)]


def _candidate_hit(kind: str, op: str, value: object, operand: Any) -> bool:  # noqa: ANN401
    if op == "empty":
        return _is_empty(value)
    if op == "not_empty":
        return not _is_empty(value)
    return value is not None and _test(kind, op, value, operand)


def _column_filled(node: Node, condition: FieldCondition) -> bool:
    """Whether some row holds a non-empty value in the table column."""
    return any(not _is_empty(value) for value in _candidates(node, condition))


def _declares(extra_schema: Mapping[str, Any] | None, key: str, kind: str) -> bool:
    """Whether the item's own overlay declares `key` with `kind` and keeps it live."""
    props = (extra_schema or {}).get("properties")
    prop = props.get(key) if isinstance(props, Mapping) else None
    meta = prop.get("x-menagerist") if isinstance(prop, Mapping) else None
    return (
        isinstance(meta, Mapping)
        and meta.get("kind") == kind
        and meta.get("archived") is not True
    )


def _scope(node: Node, condition: FieldCondition, ctx: ResolvedQuery) -> str | None:
    """The field's kind if `node` is in the condition's scope, else None."""
    if condition.field_kind is not None:
        declared = _declares(node.extra_schema, condition.key, condition.field_kind)
        return condition.field_kind if declared else None
    kind = ctx.field_kinds.get((condition.type or "", condition.key, condition.sub_key))
    return kind if node.type == condition.type else None


def _field_matches(node: Node, condition: FieldCondition, ctx: ResolvedQuery) -> bool:
    if condition in ctx.stale:
        return False
    kind = _scope(node, condition, ctx)
    if kind is None:
        return False
    positive = COMPLEMENT_OPERATORS.get(condition.op)
    if positive is not None:
        return not _field_matches(node, replace(condition, op=positive), ctx)
    if condition.sub_key is not None and condition.op in {"empty", "not_empty"}:
        return _column_filled(node, condition) == (condition.op == "not_empty")
    operand: Any = None
    if condition.value is not None:
        operand = _resolve(condition.value, node, kind, ctx.today)
        if operand is _MISSING:
            return False
    return any(
        _candidate_hit(kind, condition.op, value, operand)
        for value in _candidates(node, condition)
    )


def _date_matches(node: Node, condition: DateCondition, ctx: ResolvedQuery) -> bool:
    stamp = node.created_at if condition.on == "created" else node.updated_at
    day = stamp.astimezone(UTC).date().isoformat()
    operand = _resolve(condition.value, node, "date", ctx.today)
    if condition.op == "between":
        return bool(operand[0] <= day <= operand[1])
    return _compare(condition.op, day, operand)


def _tag_matches(node: Node, condition: TagCondition) -> bool:
    held = set(node.tags)
    wanted = set(condition.tags)
    return {
        "any": bool(held & wanted),
        "all": wanted <= held,
        "none": not held & wanted,
    }[condition.mode]


def _description_matches(node: Node, condition: DescriptionCondition) -> bool:
    if condition.op == "~":
        return fold(condition.value or "") in fold(node.description or "")
    return description_blank(node.description) == (condition.op == "empty")


def _name_matches(node: Node, condition: NameCondition) -> bool:
    if condition.op == "~":
        return fold(condition.value) in fold(node.name)
    return fold(condition.value) == fold(node.name)


def _media_matches(node: Node, condition: MediaCondition, env: QueryEnv) -> bool:
    if env.external is None:
        return False
    return env.external.media_matches(
        node.id, condition.mode, condition.type, env.scope
    )


def _collection_matches(
    node: Node, condition: CollectionCondition, ctx: ResolvedQuery, env: QueryEnv
) -> bool:
    """On any live target; `none` negates that, but all-stale matches nothing."""
    live = [t for t in condition.targets if not isinstance(t, StaleTarget)]
    if not live:
        return False
    manual = [t.id for t in live if isinstance(t, ManualTarget)]
    on_manual = (
        env.external is not None
        and bool(manual)
        and env.external.collection_matches(node.id, manual, env.scope)
    )
    on_smart = any(
        t.where is None or matches(node, t.where, ctx, env)
        for t in live
        if isinstance(t, SmartTarget)
    )
    return (on_manual or on_smart) == (condition.mode == "any")


def _item_condition(
    node: Node, condition: Condition, ctx: ResolvedQuery, env: QueryEnv
) -> bool:
    """Type, favourite, and the conditions that need other modules' data."""
    if isinstance(condition, TypeCondition):
        return node.type in condition.slugs
    if isinstance(condition, FavouriteCondition):
        return node.favourite == condition.value
    if isinstance(condition, MediaCondition):
        return _media_matches(node, condition, env)
    if isinstance(condition, CollectionCondition):
        return _collection_matches(node, condition, ctx, env)
    raise AssertionError(condition)


_ITEM_CONDITIONS = (
    TypeCondition,
    FavouriteCondition,
    MediaCondition,
    CollectionCondition,
)


def _condition(
    node: Node, condition: Condition, ctx: ResolvedQuery, env: QueryEnv
) -> bool:
    if isinstance(condition, TextCondition):
        return text_matches(node, fold(condition.q), ctx.search_exclusions)
    if isinstance(condition, DescriptionCondition):
        return _description_matches(node, condition)
    if isinstance(condition, NameCondition):
        return _name_matches(node, condition)
    if isinstance(condition, _ITEM_CONDITIONS):
        return _item_condition(node, condition, ctx, env)
    if isinstance(condition, TagCondition):
        return _tag_matches(node, condition)
    if isinstance(condition, DateCondition):
        return _date_matches(node, condition, ctx)
    return _field_matches(node, condition, ctx)


def matches(node: Node, group: Group, ctx: ResolvedQuery, env: QueryEnv) -> bool:
    """Whether `node` satisfies the filter tree."""
    results = (
        matches(node, child, ctx, env)
        if isinstance(child, Group)
        else _condition(node, child, ctx, env)
        for child in group.children
    )
    if group.op == "and":
        return all(results)
    if group.op == "or":
        return any(results)
    return not next(iter(results))


def _field_sort_value(node: Node, key: SortKey, ctx: ResolvedQuery) -> SortValue:
    kind = ctx.field_kinds.get((key.type or "", key.key or "", None))
    if kind is None or node.type != key.type:
        return None
    value = node.attributes.get(key.key or "")
    if kind in _NUMERIC:
        return _number(value)
    if kind == "money":
        return _number(value.get("value")) if isinstance(value, Mapping) else None
    if not isinstance(value, str):
        return None
    return value if kind in {"date", "partialdate"} else sort_key(value)


def sort_values(node: Node, ctx: ResolvedQuery) -> tuple[SortValue, ...]:
    """The value of each sort key for `node` (None sorts last)."""
    values: list[SortValue] = []
    for key in ctx.query.sort:
        if key.by == "name":
            values.append(sort_key(node.name))
        elif key.by == "created":
            values.append(node.created_at.timestamp())
        elif key.by == "updated":
            values.append(node.updated_at.timestamp())
        else:
            values.append(_field_sort_value(node, key, ctx))
    return tuple(values)


def _order(left: SortValue, right: SortValue, *, desc: bool) -> int:
    """Negative when `left` sorts first; None is always last."""
    if left is None and right is None:
        return 0
    if left is None:
        return 1
    if right is None:
        return -1
    result = (left > right) - (left < right)  # type: ignore[operator]
    return -result if desc else result


def is_after(hit: SearchHit, cursor: Cursor, sort: tuple[SortKey, ...]) -> bool:
    """Whether `hit` sorts strictly after the cursor row."""
    for index, key in enumerate(sort):
        order = _order(
            hit.sort_values[index], cursor.sort_values[index], desc=key.dir == "desc"
        )
        if order:
            return order > 0
    return hit.node.id > cursor.id
