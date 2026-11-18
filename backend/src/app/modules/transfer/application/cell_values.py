"""Turn the text of a spreadsheet cell into the value a field stores."""

import math
import re
from datetime import date
from typing import TYPE_CHECKING, NamedTuple

from app.modules.transfer.domain.errors import CellValueError
from app.modules.transfer.domain.tabular import DayMonthOrder, DayMonthOrderGuess

if TYPE_CHECKING:
    from collections.abc import Iterable

    from app.modules.transfer.domain.tabular import FieldSpec

_TRUE = frozenset({"yes", "y", "true", "1"})
_FALSE = frozenset({"no", "n", "false", "0"})
_PARTIAL_DATE = re.compile(r"^(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?$")
_MONTH_YEAR = re.compile(r"^(\d{1,2})/(\d{4})$")
_MONTH_NAME = re.compile(r"^([A-Za-z]+)\.?[ -](\d{2}|\d{4})$")
_THREE_PARTS = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
_MONTH_NAMES = (
    "january february march april may june july august september october november "
    + "december"
).split()
_MONTHS = {
    **{name: number for number, name in enumerate(_MONTH_NAMES, start=1)},
    **{name[:3]: number for number, name in enumerate(_MONTH_NAMES, start=1)},
    "sept": 9,
}
_DATE_HINT = "use 2019-08-19 or 19/08/2019"
_PARTIAL_HINT = "use 2019, 2019-08, 2019-08-19, 08/2019, Oct-18 or 19/08/2019"
_FULL_YEAR_DIGITS = 4
_PIVOT = 50
_MONTHS_IN_YEAR = 12


def convert_cell(
    text: str,
    field: FieldSpec,
    *,
    list_separator: str,
    day_month_order: DayMonthOrder = DayMonthOrder.DAY_FIRST,
) -> str | int | float | bool | list[str] | None:
    """Return the value `text` gives for `field`, or `None` to leave the field out.

    Raises:
        CellValueError: the text is not a valid value for the field.
    """
    if not field.importable:
        raise CellValueError(field.reason or f"{field.title} cannot be imported yet")
    text = text.strip()
    if not text:
        return None
    if field.multiple:
        return _choices(text, field, list_separator)
    if field.options is not None:
        return _choice(text, field.options)
    return _scalar(text, field, day_month_order)


def _scalar(
    text: str, field: FieldSpec, day_month_order: DayMonthOrder
) -> str | int | float | bool:
    if field.kind == "date":
        return _date(text, day_month_order)
    if field.kind == "partialdate":
        return _partial_date(text, day_month_order)
    if field.json_type == "string":
        return text
    if field.json_type in {"number", "integer"}:
        return _number(text, whole=field.json_type == "integer")
    if field.json_type == "boolean":
        return _yes_no(text)
    raise CellValueError(f"{field.title} cannot be imported yet")


def _choice(text: str, options: tuple[str, ...]) -> str:
    for option in options:
        if option.casefold() == text.casefold():
            return option
    raise CellValueError(f"'{text}' is not one of {', '.join(options)}")


def _choices(text: str, field: FieldSpec, separator: str) -> list[str]:
    options = field.options or ()
    parts = [part.strip() for part in text.split(separator) if part.strip()]
    return [_choice(part, options) for part in parts]


class _ParsedDate(NamedTuple):
    """The parts of a date as written; a month or day left out is None."""

    year: int
    month: int | None
    day: int | None


def _date(text: str, order: DayMonthOrder) -> str:
    year, month, day = _read_date(text, order, _DATE_HINT)
    if day is None:
        raise CellValueError(
            f"'{text}' has no day; a date needs one, use 2019-08-19 "
            + "(a partial date field takes a month or a year)"
        )
    return f"{year:04d}-{month:02d}-{day:02d}"


def _partial_date(text: str, order: DayMonthOrder) -> str:
    year, month, day = _read_date(text, order, _PARTIAL_HINT)
    if month is None:
        return f"{year:04d}"
    if day is None:
        return f"{year:04d}-{month:02d}"
    return f"{year:04d}-{month:02d}-{day:02d}"


def _read_date(text: str, order: DayMonthOrder, hint: str) -> _ParsedDate:
    """Return the year and, if written, the month and day of a date in any shape."""
    found = _find_date(text, order)
    if found is not None:
        year, month, day = found
        if (month is None or 1 <= month <= 12) and (
            day is None or _is_real_day(year, month or 1, day)
        ):
            return found
    raise CellValueError(f"'{text}' is not a date, {hint}")


def _find_date(text: str, order: DayMonthOrder) -> _ParsedDate | None:
    if found := _PARTIAL_DATE.match(text):
        year, month, day = found.groups()
        return _ParsedDate(int(year), _optional(month), _optional(day))
    if found := _MONTH_YEAR.match(text):
        return _ParsedDate(int(found[2]), int(found[1]), None)
    if found := _MONTH_NAME.match(text):
        month = _MONTHS.get(found[1].casefold())
        return None if month is None else _ParsedDate(_year(found[2]), month, None)
    if found := _THREE_PARTS.match(text):
        first, second = int(found[1]), int(found[2])
        if order is DayMonthOrder.DAY_FIRST:
            day, month = first, second
        else:
            day, month = second, first
        return _ParsedDate(_year(found[3]), month, day)
    return None


def _optional(digits: str | None) -> int | None:
    return None if digits is None else int(digits)


def _year(digits: str) -> int:
    """Read a year; two digits are 2000 to 2049 for 00 to 49 and 1950 to 1999 after."""
    year = int(digits)
    if len(digits) == _FULL_YEAR_DIGITS:
        return year
    return 2000 + year if year < _PIVOT else 1900 + year


def suggest_day_month_order(cells: Iterable[str]) -> DayMonthOrderGuess | None:
    """Suggest a date order from the cells written as three numbers, if there are any.

    A first number over 12 can only be a day and a second over 12 only a day in the
    other order. With neither, or with both, day first is a guess.
    """
    first_is_day = second_is_day = seen = False
    for cell in cells:
        found = _THREE_PARTS.match(cell.strip())
        if found is None:
            continue
        seen = True
        first_is_day = first_is_day or int(found[1]) > _MONTHS_IN_YEAR
        second_is_day = second_is_day or int(found[2]) > _MONTHS_IN_YEAR
    if not seen:
        return None
    if second_is_day and not first_is_day:
        return DayMonthOrderGuess(order=DayMonthOrder.MONTH_FIRST, certain=True)
    return DayMonthOrderGuess(
        order=DayMonthOrder.DAY_FIRST, certain=first_is_day and not second_is_day
    )


def _is_real_day(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


def _number(text: str, *, whole: bool) -> int | float:
    try:
        value = int(text)
    except ValueError:
        pass
    else:
        return value
    try:
        decimal = float(text)
    except ValueError:
        raise CellValueError(f"'{text}' is not a number") from None
    if not math.isfinite(decimal):
        raise CellValueError(f"'{text}' is not a number")
    if whole:
        raise CellValueError(f"'{text}' is not a whole number")
    return decimal


def _yes_no(text: str) -> bool:
    word = text.casefold()
    if word in _TRUE:
        return True
    if word in _FALSE:
        return False
    raise CellValueError(f"'{text}' is not yes or no")
