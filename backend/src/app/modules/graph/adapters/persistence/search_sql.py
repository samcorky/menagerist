"""SQL for free-text matching over nodes, shared by `list`, `count` and `search`."""

from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    ARRAY,
    Text,
    and_,
    bindparam,
    cast,
    column,
    exists,
    false,
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
_MIN_PREFILTER_LENGTH = 3
_FIRST_PRINTABLE = 0x20
# Characters `unaccent` folds to `"` or `\`. The query is folded after JSON has
# already escaped a stored quote, so a query holding one could miss a match:
# U+02BA, U+201C, U+201D, U+201F, U+2033, U+301D, U+301E, U+FF02 (to `"`) and
# U+2216, U+FE68, U+FF3C (to `\`). A test pins this list against the database.
_UNACCENT_TO_JSON_ESCAPED = frozenset(
    "\u02ba\u201c\u201d\u201f\u2033\u301d\u301e\uff02\u2216\ufe68\uff3c"
)


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


def _prefilter_is_safe(q: str) -> bool:
    r"""Whether the trigram prefilter on `attributes::text` is a safe superset for `q`.

    The prefilter tests the JSON text of `attributes`, where a value is escaped:
    `"` and `\` gain a backslash and control characters (below 0x20) become
    `\uXXXX` or `\n`-style escapes. A query holding any of those could miss
    a real match, so it skips the prefilter, as does a query holding a character
    that `unaccent` folds to `"` or `\` (see `_UNACCENT_TO_JSON_ESCAPED`).
    Queries under 3 characters are
    skipped too: they are below trigram size, so the index cannot help.
    For every other query (numbers as printed, raw unicode, `%`, `_`, `/` are
    rendered verbatim and `unaccent` works character by character), a match
    inside one value is a substring of the whole text. That holds only after
    the skip rules above.
    """
    return len(q) >= _MIN_PREFILTER_LENGTH and not any(
        c in '"\\' or ord(c) < _FIRST_PRINTABLE or c in _UNACCENT_TO_JSON_ESCAPED
        for c in q
    )


def search_clause(
    q: str, exclusions: Mapping[str, Sequence[str]] | None
) -> ColumnElement[bool]:
    """Match `q` against name, description and attribute values, per type exclusions.

    Never NULL, and shaped so the trigram indexes on name, description and
    attributes can all serve it through a bitmap OR.
    """
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
    # Never NULL, so the caller needs no COALESCE (which would hide the indexes).
    in_attributes: ColumnElement[bool] = func.coalesce(
        or_(*scans, unrestricted), false()
    )
    if _prefilter_is_safe(q):
        # A cheap superset test the trigram index can answer, in front of the walk.
        in_attributes = and_(
            unaccent_ilike(cast(attributes, Text), pattern), in_attributes
        )
    return (
        unaccent_ilike(NodeModel.name, pattern)
        | and_(
            NodeModel.description.is_not(None),
            unaccent_ilike(NodeModel.description, pattern),
        )
        | in_attributes
    )
