"""What importing a spreadsheet needs to know: limits, fields, mappings, problems."""

from dataclasses import dataclass
from enum import StrEnum


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


MAX_IMPORT_BYTES = 10 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
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


@dataclass(kw_only=True, frozen=True)
class ColumnMapping:
    """Where one column of the file goes.

    `target` is `name`, `description`, `tags`, a field key, or `None` to ignore it.
    """

    column: str
    target: str | None


@dataclass(kw_only=True, frozen=True)
class CellProblem:
    """A value in the file that cannot be imported, by spreadsheet row and field."""

    row: int
    field: str
    message: str
