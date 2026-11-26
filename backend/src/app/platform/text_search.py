"""The text filter behind a list's `q`: contains, ignoring case and accents.

The in-memory twin is `app.shared_kernel.text.fold`.
"""

from typing import TYPE_CHECKING

from sqlalchemy import func

if TYPE_CHECKING:
    from sqlalchemy import ColumnElement, SQLColumnExpression

LIKE_ESCAPE = "\\"


def contains_pattern(q: str) -> str:
    """Return a contains-pattern for `q` with LIKE wildcards escaped."""
    escaped = q.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
    escaped = escaped.replace("%", LIKE_ESCAPE + "%").replace("_", LIKE_ESCAPE + "_")
    return f"%{escaped}%"


def unaccent_ilike(
    column: SQLColumnExpression[str] | SQLColumnExpression[str | None],
    pattern: str,
) -> ColumnElement[bool]:
    """Case- and accent-insensitive LIKE of `column` against an escaped `pattern`."""
    return func.unaccent(column).ilike(func.unaccent(pattern), escape=LIKE_ESCAPE)
