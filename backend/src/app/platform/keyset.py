"""SQL keyset paging: the counterpart of `shared_kernel.paging.page_rows`.

A persistence adapter hands over its query, already limited to what the actor may
see, and the columns a list can be sorted by. The helper adds the keyset condition,
the ordering and the limit, and returns a page with the cursor of the next one. Rows
with no value for a key sort after the rest in either direction, and the id breaks
ties, exactly as `page_rows` does.

The next cursor's values are read from the database, as extra columns of the same
query, not recomputed in Python, so a row's cursor always equals what the next
comparison sees.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import SQLColumnExpression, and_, func, or_, select

from app.shared_kernel.paging import (
    Cursor,
    CursorValue,
    InvalidCursorError,
    Page,
    PageRequest,
    SortOrder,
    parse_text,
    parse_timestamp,
    timestamp_value,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Mapping

    from sqlalchemy import Select
    from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class SortColumn:
    """A column or expression a list can be sorted by."""

    expr: SQLColumnExpression[Any]
    # Reads a cursor value back into what the column compares with.
    parse: Callable[[CursorValue], Any]


def text_column(
    column: SQLColumnExpression[str] | SQLColumnExpression[str | None],
) -> SortColumn:
    """Text sorted ignoring case: the key is `lower(column)`."""
    return SortColumn(expr=func.lower(column), parse=parse_text)


def timestamp_column(
    column: SQLColumnExpression[datetime] | SQLColumnExpression[datetime | None],
) -> SortColumn:
    """A timestamp, carried in the cursor as its ISO 8601 text."""
    return SortColumn(expr=column, parse=parse_timestamp)


def _cursor_value(value: object) -> CursorValue:
    if isinstance(value, datetime):
        return timestamp_value(value)
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"{type(value).__name__} cannot be a cursor value")


def _after(
    cursor: Cursor,
    orders: tuple[SortOrder, ...],
    sorted_by: list[SortColumn],
    id_column: SQLColumnExpression[uuid.UUID],
) -> SQLColumnExpression[bool]:
    """Rows strictly after the cursor: the first key that differs decides."""
    try:
        wanted = [
            None if value is None else column.parse(value)
            for column, value in zip(sorted_by, cursor.values, strict=True)
        ]
    except (TypeError, ValueError) as exc:
        raise InvalidCursorError("The page cursor is not valid.") from exc

    clauses: list[SQLColumnExpression[bool]] = []
    same: list[SQLColumnExpression[bool]] = []
    for column, value, order in zip(sorted_by, wanted, orders, strict=False):
        expr = column.expr
        if value is not None:
            beyond = expr < value if order is SortOrder.DESC else expr > value
            clauses.append(and_(*same, or_(beyond, expr.is_(None))))
            same.append(expr == value)
        else:
            same.append(expr.is_(None))
    # The id follows the last key's direction.
    beyond_id = (
        id_column < cursor.id if orders[-1] is SortOrder.DESC else id_column > cursor.id
    )
    clauses.append(and_(*same, beyond_id))
    return or_(*clauses)


async def keyset_page[Row, T](
    session: AsyncSession,
    stmt: Select[Row],
    *,
    id_column: SQLColumnExpression[uuid.UUID],
    columns: Mapping[str, SortColumn],
    request: PageRequest,
    to_domain: Callable[[Row], T],
    with_total: bool = False,
) -> Page[T]:
    """Run `stmt` as one page of `request`: ordered, resumed after the cursor, limited.

    `stmt` selects the rows of one model, with the actor's scope and the route's
    filters applied and no ordering of its own. The keyset condition is added to it,
    so paging can never reach a row the scope left out. With `with_total` the page
    carries `total`, the rows `stmt` matches, at the price of one count query.

    Raises:
        InvalidCursorError: The cursor does not match the request, or its values are
            not of the kind the sort key compares with.
    """
    request.check()
    # Counted over the same rows, before the keyset condition narrows them to this page.
    total = (
        await session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        if with_total
        else None
    )
    sorted_by = [columns[key] for key in request.keys]
    orders = request.orders

    if request.after is not None:
        stmt = stmt.where(_after(request.after, orders, sorted_by, id_column))
    ordering = [
        (
            column.expr.desc() if order is SortOrder.DESC else column.expr.asc()
        ).nulls_last()
        for column, order in zip(sorted_by, orders, strict=False)
    ]
    ordering.append(
        id_column.desc() if orders[-1] is SortOrder.DESC else id_column.asc()
    )

    labelled = stmt.add_columns(
        *(column.expr.label(f"_key{n}") for n, column in enumerate(sorted_by)),
        id_column.label("_id"),
    )
    result = await session.execute(labelled.order_by(*ordering).limit(request.size + 1))
    rows = result.all()
    kept = rows[: request.size]
    items = [to_domain(row[0]) for row in kept]
    if not kept or len(rows) <= request.size:
        return Page(items=items, total=total)
    last = kept[-1]
    return Page(
        items=items,
        next=request.next_after(
            last[-1], tuple(_cursor_value(value) for value in last[1:-1])
        ),
        total=total,
    )
