"""Keyset paging that every list shares: the cursor, a page, and the in-memory twin.

A list is ordered by zero to `MAX_SORT_KEYS` sort keys and finally by id, each key in
its own direction and the id in the direction of the last (docs/API_STYLE.md, "Sort,
order and search"). A cursor names the last row of a page, so the next page resumes
after it: it holds the sort keys, their directions, the row's value for each key, and
the row's id.

The SQL counterpart is `app.platform.keyset`; the two answer the same questions the
same way, so an in-memory adapter and a SQL one list rows in the same order.
"""

import base64
import binascii
import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from functools import cmp_to_key
from typing import TYPE_CHECKING

from app.shared_kernel.errors import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

# What a sort key's value may be in a cursor: a JSON scalar. A timestamp is its ISO
# 8601 text, so it travels as a string and sorts the same way.
type CursorValue = str | int | float | bool | None

CURSOR_VERSION = 1

# The most rows one page returns, whatever `limit` asks for. Lists that cap `limit`
# in the API stay under it; the few that never did cannot be asked for everything.
MAX_PAGE_ROWS = 1000

# The most keys a list is sorted by at once, not counting the id.
MAX_SORT_KEYS = 3


class SortOrder(StrEnum):
    """The direction of a list's `order` parameter."""

    ASC = "asc"
    DESC = "desc"


class InvalidCursorError(ValidationError):
    """The `after` cursor cannot be read, or belongs to a different sort."""


def timestamp_value(moment: datetime) -> str:
    """The cursor text of a timestamp: ISO 8601 with fixed-width microseconds."""
    return moment.isoformat(timespec="microseconds")


@dataclass(kw_only=True, frozen=True)
class Cursor:
    """The position of the last row of a page.

    `sort` names the keys and `order` gives each one's direction; with no keys,
    `order` holds one entry for the id. `values` has one value per key, and the id
    breaks ties in the direction of the last entry of `order`.
    """

    sort: tuple[str, ...]
    order: tuple[SortOrder, ...]
    values: tuple[CursorValue, ...]
    id: uuid.UUID

    @classmethod
    def after_id(cls, row_id: uuid.UUID, order: SortOrder = SortOrder.ASC) -> Cursor:
        """The cursor for a list in its default order, resuming after `row_id`."""
        return cls(sort=(), order=(order,), values=(), id=row_id)

    def encode(self) -> str:
        """The opaque text a client passes back as `after`."""
        payload = {
            "v": CURSOR_VERSION,
            "s": list(self.sort),
            "o": [order.value for order in self.order],
            "k": list(self.values),
            "i": str(self.id),
        }
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(text: str) -> Cursor:
    """Read a cursor from the text `Cursor.encode` made.

    A bare id is the default-order cursor older clients and links carry.

    Raises:
        InvalidCursorError: The text is not a cursor.
    """
    try:
        return Cursor.after_id(uuid.UUID(text))
    except ValueError:
        pass
    try:
        raw = base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
        payload = json.loads(raw)
        if payload["v"] != CURSOR_VERSION:
            raise ValueError("version")
        sort = tuple(_text(name) for name in payload["s"])
        order = tuple(SortOrder(direction) for direction in payload["o"])
        values = tuple(_value(value) for value in payload["k"])
        cursor = Cursor(sort=sort, order=order, values=values, id=_id(payload["i"]))
        if len(values) != len(sort) or len(order) != max(len(sort), 1):
            raise ValueError("lengths")
    except (
        binascii.Error,
        KeyError,
        TypeError,
        ValueError,  # includes bad JSON, UTF-8, enum values and uuids
    ) as exc:
        raise InvalidCursorError("The page cursor is not valid.") from exc
    return cursor


def _text(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError("text")
    return value


def _value(value: object) -> CursorValue:
    if value is not None and not isinstance(value, str | int | float | bool):
        raise TypeError("value")
    return value


def _id(value: object) -> uuid.UUID:
    return uuid.UUID(_text(value))


@dataclass(kw_only=True, frozen=True)
class PageRequest:
    """Which rows a list is asked for: where to resume, how many, and in what order."""

    after: Cursor | None = None
    limit: int = 50
    sort: str | None = None
    order: SortOrder = SortOrder.ASC
    # The keys after `sort`, each with its direction. Only meaningful with a `sort`.
    then_by: tuple[tuple[str, SortOrder], ...] = ()

    @property
    def size(self) -> int:
        """The rows to return: `limit`, kept between 0 and `MAX_PAGE_ROWS`."""
        return max(0, min(self.limit, MAX_PAGE_ROWS))

    @property
    def keys(self) -> tuple[str, ...]:
        """The sort keys, none when the list is in its default order."""
        if self.sort is None:
            return ()
        return (self.sort, *(key for key, _ in self.then_by))

    @property
    def orders(self) -> tuple[SortOrder, ...]:
        """One direction per sort key, or the id's alone when there are no keys."""
        if self.sort is None:
            return (self.order,)
        return (self.order, *(order for _, order in self.then_by))

    def check(self) -> None:
        """Refuse a cursor that came from a different `sort` or `order`.

        Raises:
            InvalidCursorError: The cursor does not match this request.
        """
        after = self.after
        if after is not None and (
            after.sort != self.keys or after.order != self.orders
        ):
            raise InvalidCursorError(
                "The page cursor is from a different sort or order."
            )

    def next_after(self, last_id: uuid.UUID, values: tuple[CursorValue, ...]) -> Cursor:
        """The cursor that resumes after the row with `last_id` and `values`."""
        return Cursor(sort=self.keys, order=self.orders, values=values, id=last_id)


@dataclass(kw_only=True, frozen=True)
class SortBy[Sort: StrEnum]:
    """A sort key after the first, with its own direction."""

    key: Sort
    order: SortOrder = SortOrder.ASC


@dataclass(kw_only=True)
class PagedQuery[Sort: StrEnum]:
    """The paging fields every list query shares; a list adds its own filters.

    `Sort` is the enum of keys the list can sort by. `sort` and `order` are the first
    key and its direction, and `then_by` the keys after it. A list that runs in
    another order by default overrides `order`.
    """

    after: Cursor | None = None
    limit: int = 50
    sort: Sort | None = None
    order: SortOrder = SortOrder.ASC
    then_by: tuple[SortBy[Sort], ...] = ()

    def page_request(self, default_sort: Sort | None = None) -> PageRequest:
        """This query as a `PageRequest`, sorted by `default_sort` if none is given."""
        sort = self.sort or default_sort
        return PageRequest(
            after=self.after,
            limit=self.limit,
            sort=None if sort is None else sort.value,
            order=self.order,
            then_by=tuple((by.key.value, by.order) for by in self.then_by),
        )


@dataclass(kw_only=True)
class SearchedPagedQuery[Sort: StrEnum](PagedQuery[Sort]):
    """`PagedQuery` for a list with text to search: `q` keeps the rows containing it."""

    q: str | None = None


@dataclass(kw_only=True, frozen=True)
class Page[T]:
    """One page of rows, and the cursor of the next page when there is one."""

    items: list[T]
    next: Cursor | None = None
    # How many rows matched before paging, when the helper that made the page knows.
    total: int | None = None


def _compare(
    left: Sequence[CursorValue],
    right: Sequence[CursorValue],
    orders: Sequence[SortOrder],
) -> int:
    """Order two rows' (values..., id) as the list does: empty last, id breaks ties."""
    for a, b, order in zip(left, right, orders, strict=True):
        if a == b:
            continue
        if a is None or b is None:
            return 1 if a is None else -1
        outcome = -1 if a < b else 1  # type: ignore[operator]
        return outcome if order is SortOrder.ASC else -outcome
    return 0


def page_rows[T, Key: str](
    rows: Sequence[T],
    request: PageRequest,
    *,
    id_of: Callable[[T], uuid.UUID],
    values: Mapping[Key, Callable[[T], CursorValue]],
) -> Page[T]:
    """Order `rows`, resume after the cursor, and take one page: the in-memory twin.

    `values` gives each sort key's value for a row, keyed by name or by the enum of
    the list's keys. Rows with no value for a key sort after the rest in either
    direction, and the id breaks ties. The page carries `total`, the rows given.

    Raises:
        InvalidCursorError: The cursor does not match the request's sort and order.
    """
    request.check()
    keys = request.keys
    # Each key in its own direction; the id follows the last of them.
    orders = (*request.orders[: len(keys)], request.orders[-1])

    getters = {str(key): getter for key, getter in values.items()}
    positioned = [
        ((*(getters[key](row) for key in keys), str(id_of(row))), row) for row in rows
    ]

    def by_position(
        a: tuple[tuple[CursorValue, ...], T], b: tuple[tuple[CursorValue, ...], T]
    ) -> int:
        return _compare(a[0], b[0], orders)

    positioned.sort(key=cmp_to_key(by_position))
    after = request.after
    if after is not None:
        resume = (*after.values, str(after.id))
        positioned = [p for p in positioned if _compare(p[0], resume, orders) > 0]
    page = positioned[: request.size]
    if not page or len(positioned) <= request.size:
        return Page(items=[row for _, row in page], total=len(rows))
    last_position, last_row = page[-1]
    return Page(
        items=[row for _, row in page],
        next=request.next_after(id_of(last_row), last_position[:-1]),
        total=len(rows),
    )


def parse_timestamp(value: CursorValue) -> datetime:
    """Read a timestamp key's cursor value.

    Raises:
        TypeError: The value is not text.
        ValueError: The text is not an ISO 8601 timestamp.
    """
    if not isinstance(value, str):
        raise TypeError("timestamp")
    return datetime.fromisoformat(value)


def parse_text(value: CursorValue) -> str:
    """Read a text key's cursor value.

    Raises:
        TypeError: The value is not text.
    """
    if not isinstance(value, str):
        raise TypeError("text")
    return value
