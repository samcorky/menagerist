import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from app.shared_kernel.paging import (
    MAX_PAGE_ROWS,
    Cursor,
    InvalidCursorError,
    Page,
    PageRequest,
    SortOrder,
    decode_cursor,
    page_rows,
    parse_text,
    parse_timestamp,
    timestamp_value,
)


@dataclass(frozen=True)
class Row:
    """A row with an id and an optional name to sort by."""

    id: uuid.UUID
    name: str | None


def _rows(*names: str | None) -> list[Row]:
    """Rows with increasing ids, so id order is the order they are given in."""
    return [Row(id=uuid.uuid7(), name=name) for name in names]


def _page(rows: list[Row], request: PageRequest) -> Page[Row]:
    return page_rows(
        rows,
        request,
        id_of=lambda row: row.id,
        values={"name": lambda row: row.name.lower() if row.name else None},
    )


def _walk(rows: list[Row], **options: object) -> list[list[str | None]]:
    """Follow the cursors to the end, returning the names on each page."""
    pages: list[list[str | None]] = []
    request = PageRequest(**options)  # type: ignore[arg-type]
    while True:
        page = _page(rows, request)
        pages.append([row.name for row in page.items])
        if page.next is None:
            return pages
        request = PageRequest(
            after=decode_cursor(page.next.encode()),
            limit=request.limit,
            sort=request.sort,
            order=request.order,
        )


@pytest.mark.fast
def test_a_cursor_survives_being_encoded_and_decoded() -> None:
    """The text is what a client passes back, so it reads back to the same cursor."""
    cursor = Cursor(
        sort=("name",),
        order=(SortOrder.DESC,),
        values=("nebula",),
        id=uuid.uuid7(),
    )

    assert decode_cursor(cursor.encode()) == cursor


@pytest.mark.fast
def test_a_cursor_is_url_safe_text() -> None:
    """It goes in a query string and a `Link` header unescaped."""
    cursor = Cursor.after_id(uuid.uuid7())

    assert cursor.encode().replace("-", "").replace("_", "").isalnum()


@pytest.mark.fast
def test_a_bare_id_is_a_cursor_in_the_default_order() -> None:
    """Links and scripts from before sorting existed keep working."""
    row_id = uuid.uuid7()

    assert decode_cursor(str(row_id)) == Cursor.after_id(row_id)


def _encode(payload: object) -> str:
    raw = json.dumps(payload).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


_GOOD = {"v": 1, "s": ["name"], "o": ["asc"], "k": ["a"], "i": str(uuid.uuid7())}


@pytest.mark.fast
@pytest.mark.parametrize(
    "text",
    [
        "",
        "not a cursor",
        "ünïcode",
        _encode(["a list"]),
        _encode({**_GOOD, "v": 2}),
        _encode({**_GOOD, "s": "name"}),
        _encode({**_GOOD, "s": [1]}),
        _encode({**_GOOD, "o": ["sideways"]}),
        _encode({**_GOOD, "k": [{"nested": True}]}),
        _encode({**_GOOD, "k": []}),
        _encode({**_GOOD, "o": ["asc", "desc"]}),
        _encode({**_GOOD, "i": "not-a-uuid"}),
        _encode({**_GOOD, "i": 7}),
        _encode({k: v for k, v in _GOOD.items() if k != "i"}),
        base64.urlsafe_b64encode(b"\xff\xfe").decode(),
    ],
)
def test_an_unreadable_cursor_is_refused(text: str) -> None:
    """A malformed or tampered cursor is a 400, never a 500."""
    with pytest.raises(InvalidCursorError):
        decode_cursor(text)


@pytest.mark.fast
@pytest.mark.parametrize(
    "cursor",
    [
        Cursor.after_id(uuid.uuid7()),
        Cursor(sort=("name",), order=(SortOrder.DESC,), values=("a",), id=uuid.uuid7()),
    ],
)
def test_a_cursor_from_another_sort_or_order_is_refused(cursor: Cursor) -> None:
    """A cursor is only good for the sort and order that made it."""
    with pytest.raises(InvalidCursorError):
        PageRequest(after=cursor, sort="name", order=SortOrder.ASC).check()


@pytest.mark.fast
def test_a_cursor_that_matches_the_request_is_accepted() -> None:
    """The check passes when sort and order agree."""
    cursor = Cursor(
        sort=("name",), order=(SortOrder.DESC,), values=("a",), id=uuid.uuid7()
    )

    PageRequest(after=cursor, sort="name", order=SortOrder.DESC).check()
    PageRequest(after=None).check()


@pytest.mark.fast
def test_the_default_order_is_by_id_and_order_flips_it() -> None:
    """With no sort the list runs oldest first, and `desc` runs newest first."""
    rows = _rows("a", "b", "c")

    assert [r.name for r in _page(rows, PageRequest()).items] == ["a", "b", "c"]
    assert [r.name for r in _page(rows, PageRequest(order=SortOrder.DESC)).items] == [
        "c",
        "b",
        "a",
    ]


@pytest.mark.fast
def test_sorting_by_a_key_ignores_case_through_the_key_function() -> None:
    """The page follows the value the key function gives, not the stored text."""
    rows = _rows("banana", "Apple", "cherry")

    names = [r.name for r in _page(rows, PageRequest(sort="name")).items]

    assert names == ["Apple", "banana", "cherry"]


@pytest.mark.fast
@pytest.mark.parametrize(
    ("order", "expected"),
    [
        (SortOrder.ASC, ["a", "b", None, None]),
        (SortOrder.DESC, ["b", "a", None, None]),
    ],
)
def test_rows_with_no_value_sort_last_in_either_direction(
    order: SortOrder, expected: list[str | None]
) -> None:
    """Empty values never lead a list, ascending or descending."""
    rows = _rows(None, "a", None, "b")

    names = [r.name for r in _page(rows, PageRequest(sort="name", order=order)).items]

    assert names == expected


@pytest.mark.fast
def test_ties_keep_a_fixed_order_by_id_in_the_direction_of_order() -> None:
    """Rows that tie on the key come in id order, reversed with `desc`."""
    rows = _rows("same", "same", "same")

    ascending = _page(rows, PageRequest(sort="name")).items
    descending = _page(rows, PageRequest(sort="name", order=SortOrder.DESC)).items

    assert [r.id for r in ascending] == [r.id for r in rows]
    assert [r.id for r in descending] == [r.id for r in reversed(rows)]


@pytest.mark.fast
@pytest.mark.parametrize("order", list(SortOrder))
@pytest.mark.parametrize("sort", [None, "name"])
@pytest.mark.parametrize("limit", [1, 2, 3, 100])
def test_following_the_cursors_visits_every_row_once_in_order(
    sort: str | None, order: SortOrder, limit: int
) -> None:
    """No page repeats a row or skips one, whatever the sort, direction or size."""
    rows = _rows("b", None, "a", "b", None, "c", "a")
    everything = [
        r.id for r in _page(rows, PageRequest(sort=sort, order=order, limit=100)).items
    ]

    seen: list[uuid.UUID] = []
    request = PageRequest(sort=sort, order=order, limit=limit)
    while True:
        page = _page(rows, request)
        seen.extend(r.id for r in page.items)
        if page.next is None:
            break
        request = PageRequest(after=page.next, sort=sort, order=order, limit=limit)

    assert seen == everything
    assert sorted(seen) == sorted(r.id for r in rows)


@pytest.mark.fast
def test_the_last_page_has_no_next_cursor() -> None:
    """A page that reaches the end of the list says so."""
    rows = _rows("a", "b")

    assert _page(rows, PageRequest(limit=2)).next is None
    assert _page(rows, PageRequest(limit=1)).next is not None
    assert _page([], PageRequest()).items == []


@pytest.mark.fast
def test_a_cursor_stays_valid_when_its_row_is_gone() -> None:
    """Resuming does not need the last row to still exist."""
    rows = _rows("a", "b", "c", "d")
    first = _page(rows, PageRequest(sort="name", limit=2))
    assert first.next is not None

    remaining = [r for r in rows if r.name != "b"]
    second = _page(remaining, PageRequest(after=first.next, sort="name", limit=2))

    assert [r.name for r in second.items] == ["c", "d"]


@pytest.mark.fast
def test_the_walk_helper_matches_the_expected_pages() -> None:
    """Two to a page, sorted descending, with the empty value last."""
    rows = _rows("a", None, "c", "b")

    pages = _walk(rows, sort="name", order=SortOrder.DESC, limit=2)

    assert pages == [["c", "b"], ["a", None]]


@pytest.mark.fast
def test_timestamps_are_fixed_width_text_that_reads_back() -> None:
    """A whole second and a fractional one sort as text the way they do as times."""
    whole = datetime(2026, 11, 26, 9, 0, 5, tzinfo=UTC)
    fraction = datetime(2026, 11, 26, 9, 0, 5, 500000, tzinfo=UTC)

    assert timestamp_value(whole) < timestamp_value(fraction)
    assert parse_timestamp(timestamp_value(fraction)) == fraction


@pytest.mark.fast
def test_a_key_value_of_the_wrong_kind_is_refused_by_the_parsers() -> None:
    """A number is not text, and text that is not a time is not a timestamp."""
    assert parse_text("nebula") == "nebula"
    with pytest.raises(TypeError):
        parse_text(7)
    with pytest.raises(TypeError):
        parse_timestamp(7)
    with pytest.raises(ValueError, match="Invalid isoformat"):
        parse_timestamp("yesterday")


@pytest.mark.fast
@pytest.mark.parametrize(
    ("limit", "size"),
    [(-5, 0), (0, 0), (7, 7), (MAX_PAGE_ROWS, MAX_PAGE_ROWS), (10**9, MAX_PAGE_ROWS)],
)
def test_a_page_never_returns_more_than_the_maximum_or_fewer_than_none(
    limit: int, size: int
) -> None:
    """A huge or negative `limit` is clamped, so it cannot ask for every row."""
    assert PageRequest(limit=limit).size == size


@pytest.mark.fast
def test_a_huge_limit_returns_a_page_of_at_most_the_maximum() -> None:
    """The page is cut at the maximum and points to the rest."""
    rows = _rows(*[str(n) for n in range(MAX_PAGE_ROWS + 5)])

    page = _page(rows, PageRequest(limit=10**9))

    assert len(page.items) == MAX_PAGE_ROWS
    assert page.next is not None
