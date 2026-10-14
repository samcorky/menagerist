"""SQL for free-text matching over nodes, shared by `list`, `count` and `search`."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    Text,
    and_,
    bindparam,
    column,
    exists,
    func,
    literal,
    literal_column,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.modules.graph.adapters.persistence.models import NodeModel

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from sqlalchemy import ColumnElement, SQLColumnExpression

LIKE_ESCAPE = "\\"


def like_pattern(q: str) -> str:
    """Return a contains-pattern for `q` with LIKE wildcards escaped."""
    escaped = q.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    escaped = escaped.replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def unaccent_ilike(
    column_: SQLColumnExpression[Any], pattern: str
) -> ColumnElement[bool]:
    """Case- and accent-insensitive LIKE of `column_` against an escaped `pattern`.

    Uses `immutable_unaccent` so the trigram indexes on name and description apply.
    """
    return func.immutable_unaccent(column_).ilike(
        func.immutable_unaccent(pattern), escape=LIKE_ESCAPE
    )


def has_matching_row(
    attributes: SQLColumnExpression[Any], key: str, sub_key: str, value: str | None
) -> ColumnElement[bool]:
    """Whether any row of group array `key` holds `sub_key`, optionally == `value`."""
    elements = func.jsonb_array_elements(attributes[key]).table_valued(
        column("value", JSONB), name="elem"
    )
    row = elements.c.value
    conditions = [row.has_key(sub_key)]
    if value is not None:
        conditions.append(row.contains({sub_key: value}))
    return exists(select(literal(1)).select_from(elements).where(*conditions))


def has_matching_value(
    attributes: SQLColumnExpression[Any], pattern: str
) -> ColumnElement[bool]:
    """Whether any string or number anywhere inside `attributes` matches `pattern`.

    Walks every nested value; key names, booleans and nulls never match.
    """
    value = func.jsonb_path_query(
        attributes, literal_column("'strict $.**'")
    ).column_valued("v")
    text_value = value.op("#>>")(literal_column("'{}'"))
    return exists(
        select(literal(1)).where(
            func.jsonb_typeof(value).in_(("string", "number")),
            unaccent_ilike(text_value, pattern),
        )
    )


def search_clause(
    q: str, exclusions: Mapping[str, Sequence[str]] | None
) -> ColumnElement[bool]:
    """Match `q` against name, description and attribute values, per type exclusions."""
    pattern = like_pattern(q)
    attributes = NodeModel.attributes
    excluded = {slug: list(keys) for slug, keys in (exclusions or {}).items() if keys}
    scans = [
        and_(
            NodeModel.type == slug,
            has_matching_value(
                attributes.op("-")(bindparam(f"excl_{i}", keys, type_=ARRAY(Text))),
                pattern,
            ),
        )
        for i, (slug, keys) in enumerate(excluded.items())
    ]
    unrestricted = has_matching_value(attributes, pattern)
    if excluded:
        unrestricted = and_(
            or_(NodeModel.type.is_(None), NodeModel.type.not_in(list(excluded))),
            unrestricted,
        )
    return (
        unaccent_ilike(NodeModel.name, pattern)
        | unaccent_ilike(NodeModel.description, pattern)
        | or_(*scans, unrestricted)
    )
