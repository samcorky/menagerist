"""Turn the text of a spreadsheet cell into the value a field stores."""

import math
import re
from datetime import date
from typing import TYPE_CHECKING

from app.modules.transfer.domain.errors import CellValueError

if TYPE_CHECKING:
    from app.modules.transfer.domain.tabular import FieldSpec

_TRUE = frozenset({"yes", "y", "true", "1"})
_FALSE = frozenset({"no", "n", "false", "0"})
_PARTIAL_DATE = re.compile(r"^(\d{4})(?:-(0[1-9]|1[0-2])(?:-(0[1-9]|[12]\d|3[01]))?)?$")
_FULL_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def convert_cell(
    text: str, field: FieldSpec, *, list_separator: str
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
    return _scalar(text, field)


def _scalar(text: str, field: FieldSpec) -> str | int | float | bool:
    if field.kind == "date":
        return _date(text)
    if field.kind == "partialdate":
        return _partial_date(text)
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


def _date(text: str) -> str:
    try:
        if _FULL_DATE.match(text):
            date.fromisoformat(text)
            return text
    except ValueError:
        pass
    raise CellValueError(f"'{text}' is not a date, use 2019-08-19")


def _partial_date(text: str) -> str:
    found = _PARTIAL_DATE.match(text)
    if found is not None:
        year, month, day = found.groups()
        if day is None or _is_real_day(int(year), int(month), int(day)):
            return text
    raise CellValueError(f"'{text}' is not a date, use 2019, 2019-08 or 2019-08-19")


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
