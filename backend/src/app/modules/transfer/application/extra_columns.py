"""Columns kept as imported items' own fields: their definition and a guessed kind."""

import re
from typing import TYPE_CHECKING, Any, Final

from app.modules.transfer.application.cell_values import convert_cell
from app.modules.transfer.domain.errors import CellValueError, InvalidImportFileError
from app.modules.transfer.domain.tabular import (
    MAX_CHOICE_OPTIONS,
    DayMonthOrder,
    ExtraField,
    ExtraFieldKind,
    FieldSpec,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

# The same rule the item page's date-in-parts field writes.
PARTIAL_DATE_PATTERN: Final = (
    "^[0-9]{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12][0-9]|3[01]))?)?$"
)
# What the frontend's field keys look like; `__proto__` and `constructor` would be
# found on every object there.
_KEY = re.compile(r"[a-z0-9_]{1,64}")
_RESERVED_KEYS = frozenset({"__proto__", "constructor"})

# Each kind's JSON Schema, as the item page's Add field writes it.
_SHAPES: Final[dict[ExtraFieldKind, dict[str, Any]]] = {
    ExtraFieldKind.TEXT: {"type": "string"},
    ExtraFieldKind.NUMBER: {"type": "number"},
    ExtraFieldKind.BOOLEAN: {"type": "boolean"},
    ExtraFieldKind.DATE: {"type": "string", "format": "date"},
    ExtraFieldKind.PARTIAL_DATE: {"type": "string", "pattern": PARTIAL_DATE_PATTERN},
    ExtraFieldKind.CHOICE: {"type": "string"},
}
# Tried in order; text takes anything, so it is the last resort.
_GUESSES: Final = (
    ExtraFieldKind.NUMBER,
    ExtraFieldKind.BOOLEAN,
    ExtraFieldKind.DATE,
    ExtraFieldKind.PARTIAL_DATE,
)


def check_key(key: str) -> None:
    """Refuse a key the frontend could not use.

    Raises:
        InvalidImportFileError: the key is not lowercase letters, digits and `_`.
    """
    if not _KEY.fullmatch(key) or key in _RESERVED_KEYS:
        raise InvalidImportFileError(f"'{key}' is not a usable key for a field.")


def choice_options(cells: Iterable[str], title: str) -> tuple[str, ...]:
    """The column's different values, in the order they first appear.

    Raises:
        InvalidImportFileError: there are more than a choice should offer.
    """
    options: dict[str, None] = {}
    for cell in cells:
        if text := cell.strip():
            options[text] = None
    if len(options) > MAX_CHOICE_OPTIONS:
        raise InvalidImportFileError(
            f"{title} has more than {MAX_CHOICE_OPTIONS} different values; "
            + "keep it as text."
        )
    return tuple(options)


def extra_property(field: ExtraField, options: tuple[str, ...] = ()) -> dict[str, Any]:
    """The JSON Schema property an item keeps for `field`."""
    prop: dict[str, Any] = {"title": field.title, **_SHAPES[field.kind]}
    if field.kind is ExtraFieldKind.CHOICE:
        prop["enum"] = list(options)
    prop["x-menagerist"] = {"kind": str(field.kind)}
    return prop


def extra_spec(field: ExtraField, options: tuple[str, ...] = ()) -> FieldSpec:
    """`field` as the cell conversion needs it."""
    shape = _SHAPES[field.kind]
    return FieldSpec(
        key=field.key,
        title=field.title,
        json_type=shape["type"],
        kind=str(field.kind),
        options=options if field.kind is ExtraFieldKind.CHOICE else None,
    )


def suggest_kind(
    cells: Iterable[str], day_month_order: DayMonthOrder
) -> ExtraFieldKind:
    """The first kind that takes every value in the column; text when none does."""
    values = [cell for cell in cells if cell.strip()]
    if not values:
        return ExtraFieldKind.TEXT
    for kind in _GUESSES:
        spec = extra_spec(ExtraField(key="guess", title="guess", kind=kind))
        try:
            for value in values:
                convert_cell(
                    value, spec, list_separator=",", day_month_order=day_month_order
                )
        except CellValueError:
            continue
        return kind
    return ExtraFieldKind.TEXT
