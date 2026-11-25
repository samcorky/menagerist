"""What importing a spreadsheet needs to know: limits, fields, mappings, problems."""

from dataclasses import dataclass
from enum import StrEnum

from app.modules.transfer.domain.bundle import NameLookup


class CsvEncoding(StrEnum):
    """The encodings a CSV file is read in."""

    UTF_8 = "utf_8"
    UTF_16 = "utf_16"
    WINDOWS_1252 = "windows_1252"

    @property
    def codec(self) -> str:
        """The name of the Python codec that reads it (UTF-8 also drops a mark)."""
        return _CODECS[self]


_CODECS = {
    CsvEncoding.UTF_8: "utf-8-sig",
    CsvEncoding.UTF_16: "utf-16",
    CsvEncoding.WINDOWS_1252: "cp1252",
}


class DayMonthOrder(StrEnum):
    """Which of the first two numbers of `03/04/2019` is the day."""

    DAY_FIRST = "day_first"
    MONTH_FIRST = "month_first"


@dataclass(kw_only=True, frozen=True)
class DayMonthOrderGuess:
    """A suggested date order, and whether the values prove it."""

    order: DayMonthOrder
    certain: bool


MAX_IMPORT_BYTES = 50 * 1024 * 1024
MAX_IMPORT_ROWS = 50_000
# Problems a preview lists by name; the rest are counted.
MAX_LISTED_PROBLEMS = 20


@dataclass(kw_only=True, frozen=True, eq=False)
class FieldSpec:
    """One field of an item type, as an import needs to fill it.

    `json_type` is the schema's `type` and `kind` the field's kind (such as
    `partialdate`). `options` are the allowed choices, and `multiple` is set when a
    cell may hold several of them. A field the import cannot fill is not
    `importable`, and `reason` says why.
    """

    key: str
    title: str
    json_type: str | None
    kind: str | None
    options: tuple[str, ...] | None
    multiple: bool = False
    importable: bool = True
    reason: str | None = None


class ExtraFieldKind(StrEnum):
    """The kinds a column kept as the items' own field can be."""

    TEXT = "text"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATE = "date"
    PARTIAL_DATE = "partialdate"
    CHOICE = "choice"


# An item's own fields, as the graph module allows.
MAX_EXTRA_FIELDS = 50
# A column kept as a choice offers each different value; past this, keep it as text.
MAX_CHOICE_OPTIONS = 50


@dataclass(kw_only=True, frozen=True)
class ExtraField:
    """A field each imported item gets for itself, filled from one column."""

    key: str
    title: str
    kind: ExtraFieldKind


@dataclass(kw_only=True, frozen=True)
class ColumnKind:
    """The kind a column's values suggest, should it be kept as an extra field."""

    column: str
    kind: ExtraFieldKind


@dataclass(kw_only=True, frozen=True)
class ColumnMapping:
    """Where one column of the file goes.

    `target` is `name`, `description`, `tags`, a field key, or `None` to ignore it.
    With `extra`, the column becomes each item's own field instead, and `target` is
    `None`.
    """

    column: str
    target: str | None
    extra: ExtraField | None = None


@dataclass(kw_only=True, frozen=True)
class CellProblem:
    """A value in the file that cannot be imported, by spreadsheet row and field."""

    row: int
    field: str
    message: str


class ConnectionEnd(StrEnum):
    """Which end of a connection the row's own item is."""

    SOURCE = "source"
    TARGET = "target"


# Columns one import may connect; each may name one item per row.
MAX_CONNECTION_COLUMNS = 5


@dataclass(kw_only=True, frozen=True)
class ConnectionColumn:
    """A column naming, on each row, an item of `item_type` the row connects to.

    The name is looked up within `item_type`, ignoring case and spacing; with no
    match the item is created or left out, as `on_missing` says.
    """

    column: str
    relationship_type: str
    item_type: str
    row_end: ConnectionEnd
    on_missing: NameLookup = NameLookup.CREATE
